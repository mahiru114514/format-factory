import asyncio
from contextlib import asynccontextmanager
from email.parser import BytesParser
from email.policy import default

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse

from .config import Settings
from .engines import capabilities, readiness
from .manager import JobManager
from .validation import normalize, safe_filename, validate_options, validate_pair


async def read_multipart(request, settings):
    """Bounded memory-only multipart: no spool file before consent is checked.

    Framework UploadFile parsing may spool large files to disk before reading the
    consent field. This endpoint deliberately does not use that parser.
    """
    content_type = request.headers.get('content-type', '')
    if not content_type.lower().startswith('multipart/form-data;') or '\r' in content_type or '\n' in content_type:
        raise HTTPException(400, '需要 multipart/form-data 上传。')
    maximum = settings.max_upload_bytes + 65536
    if request.headers.get('content-length', '').isdigit() and int(request.headers['content-length']) > maximum:
        raise HTTPException(413, '上传超过大小限制。')
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > maximum:
            raise HTTPException(413, '上传超过大小限制。')
        body.extend(chunk)
    message = BytesParser(policy=default).parsebytes(b'Content-Type: ' + content_type.encode('ascii') + b'\r\nMIME-Version: 1.0\r\n\r\n' + body)
    if not message.is_multipart() or message.defects:
        raise HTTPException(400, 'multipart 数据无效。')
    fields, uploaded = {}, None
    parts = list(message.iter_parts())
    if len(parts) > 6:
        raise HTTPException(400, '上传字段过多。')
    for part in parts:
        name = part.get_param('name', header='content-disposition')
        content = part.get_payload(decode=True)
        if content is None or part.is_multipart() or part.defects:
            raise HTTPException(400, '上传字段无效。')
        if name == 'file':
            if uploaded is not None:
                raise HTTPException(400, '每个任务仅支持一个文件。')
            if len(content) > settings.max_upload_bytes:
                raise HTTPException(413, '文件超过大小限制。')
            uploaded = (part.get_filename(), content)
        elif name in ('category', 'target', 'options', 'consent') and name not in fields and len(content) <= 8192:
            try:
                fields[name] = content.decode('utf-8')
            except UnicodeError as error:
                raise HTTPException(400, '上传字段必须是 UTF-8。') from error
        else:
            raise HTTPException(400, '上传字段无效或重复。')
    if fields.get('consent') != 'true':
        raise HTTPException(403, '需要明确同意上传文件并由服务处理。')
    if uploaded is None:
        raise HTTPException(400, '缺少上传文件。')
    return fields, uploaded


def create_app(settings=None):
    settings = settings or Settings.from_env()
    manager = JobManager(settings)

    @asynccontextmanager
    async def lifespan(app):
        manager.start()
        try:
            yield
        finally:
            manager.close()

    application = FastAPI(title='Format Factory mobile service', version='1.0', lifespan=lifespan)
    application.state.jobs = manager
    upload_slots = asyncio.Semaphore(settings.max_workers + 1)

    @application.get('/v1/capabilities')
    def get_capabilities():
        return capabilities(settings)

    @application.post('/v1/jobs', status_code=202)
    async def create_job(request: Request):
        async with upload_slots:
            fields, (name, data) = await read_multipart(request, settings)
            try:
                stem, source = safe_filename(name)
                category, target = fields.get('category', ''), normalize(fields.get('target', ''))
                validate_pair(category, source, target)
                options = validate_options(fields.get('options', '{}'), category)
                await asyncio.to_thread(manager.validate_input, data, source, options)
                ready, message = readiness(category, source, target, options)
                if not ready:
                    raise HTTPException(503, message)
                return manager.create(data, stem, source, category, target, options)
            except ValueError as error:
                raise HTTPException(400, str(error)) from error
            except TimeoutError as error:
                raise HTTPException(408, str(error)) from error
            except OverflowError as error:
                raise HTTPException(429, str(error)) from error

    def authorized_job(identifier, request):
        authorization = request.headers.get('authorization', '')
        scheme, _, token = authorization.partition(' ')
        if scheme.lower() != 'bearer' or not token or len(token) > 256:
            raise HTTPException(401, '需要任务访问令牌。', headers={'WWW-Authenticate': 'Bearer'})
        job = manager.authorized(identifier, token)
        if job is None:
            raise HTTPException(404, '任务不存在、令牌不匹配或已过期。')
        return job

    @application.get('/v1/jobs/{identifier}')
    def get_job(identifier: str, request: Request):
        job = authorized_job(identifier, request)
        with manager.lock:
            return job.status()

    @application.get('/v1/jobs/{identifier}/result')
    def get_result(identifier: str, request: Request):
        job = authorized_job(identifier, request)
        with manager.lock:
            if job.state != 'succeeded':
                raise HTTPException(409, '转换尚未成功完成。')
            return FileResponse(job.directory / 'result.zip', media_type='application/zip',
                                filename=job.stem + '.zip', headers={'Cache-Control': 'no-store'})

    @application.delete('/v1/jobs/{identifier}', status_code=204)
    def delete_job(identifier: str, request: Request):
        job = authorized_job(identifier, request)
        manager.delete(job.id)
        return Response(status_code=204)

    @application.middleware('http')
    async def private_response(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    return application


app = create_app()
