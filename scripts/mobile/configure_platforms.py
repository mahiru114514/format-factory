"""Prepare native metadata, app icons, and the self-contained iOS share target."""
import hashlib
import json
from pathlib import Path
import plistlib
import re
from xml.etree import ElementTree as ET

from openstep_parser import OpenStepDecoder
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
MOBILE = ROOT / 'mobile'
IOS = MOBILE / 'ios'
APP_ID = 'dev.formatfactory.mobile'
GROUP = 'group.' + APP_ID

def plist(path, values):
    current = plistlib.loads(path.read_bytes()) if path.exists() else {}
    current.update(values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(current, sort_keys=False))

plist(IOS / 'Runner/Info.plist', {
    'CFBundleDisplayName': '格式转换工厂', 'AppGroupId': '$(CUSTOM_GROUP_ID)',
    'NSCameraUsageDescription': '拍摄需要识别的文字、公式或需要转换的照片。',
    'NSPhotoLibraryUsageDescription': '选择需要转换或识别的照片，文件仅在确认联网处理后上传。',
    'NSPhotoLibraryAddUsageDescription': '将转换后的图片保存到相册。',
    'NSLocalNetworkUsageDescription': '连接你在设置中指定的局域网转换服务。',
    'FlutterDeepLinkingEnabled': False,
    'CFBundleURLTypes': [{'CFBundleTypeRole': 'Editor', 'CFBundleURLSchemes': ['ShareMedia-$(PRODUCT_BUNDLE_IDENTIFIER)']}],
    'NSAppTransportSecurity': {
        'NSAllowsLocalNetworking': True,
        'NSExceptionDomains': {host: {'NSExceptionAllowsInsecureHTTPLoads': True}
                               for host in ('127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '::1')},
    },
})
plist(IOS / 'ShareExtension/Info.plist', {
    'CFBundleDevelopmentRegion': 'zh_CN', 'CFBundleDisplayName': '格式转换工厂',
    'CFBundleExecutable': '$(EXECUTABLE_NAME)', 'CFBundleIdentifier': '$(PRODUCT_BUNDLE_IDENTIFIER)',
    'CFBundleInfoDictionaryVersion': '6.0', 'CFBundleName': '$(PRODUCT_NAME)',
    'CFBundlePackageType': 'XPC!', 'CFBundleShortVersionString': '$(MARKETING_VERSION)',
    'CFBundleVersion': '$(CURRENT_PROJECT_VERSION)', 'AppGroupId': '$(CUSTOM_GROUP_ID)',
    'NSExtension': {
        'NSExtensionPointIdentifier': 'com.apple.share-services',
        'NSExtensionPrincipalClass': '$(PRODUCT_MODULE_NAME).ShareViewController',
        'NSExtensionAttributes': {'NSExtensionActivationRule': {
            'NSExtensionActivationSupportsText': True,
            'NSExtensionActivationSupportsImageWithMaxCount': 20,
            'NSExtensionActivationSupportsFileWithMaxCount': 20,
        }},
    },
})
plist(IOS / 'ShareExtension/ShareExtension.entitlements', {'com.apple.security.application-groups': ['$(CUSTOM_GROUP_ID)']})

project_path = IOS / 'Runner.xcodeproj/project.pbxproj'
with project_path.open(encoding='utf-8') as source:
    project = OpenStepDecoder.ParseFromFile(source)
objects = project['objects']
def identifier(name):
    return hashlib.sha1(('factory:' + name).encode()).hexdigest().upper()[:24]
def add(purpose, **values):
    key = identifier(purpose)
    objects[key] = values
    return key
def append_unique(sequence, item):
    if item not in sequence:
        sequence.append(item)

# CocoaPods hosts ML Kit. Remove the generated SPM package target/reference so
# Xcode does not require an absent ephemeral package before pod installation.
removed = {key for key, value in objects.items() if 'FlutterGeneratedPluginSwiftPackage' in str(value)}
for key in removed:
    objects.pop(key, None)
def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value if not isinstance(v, str) or v not in removed]
    return value
project = clean(project)
objects = project['objects']
native = next(value for value in objects.values() if value.get('isa') == 'PBXNativeTarget' and value.get('name') == 'Runner')
project_object = objects[project['rootObject']]
root_group = objects[project_object['mainGroup']]
products = objects[project_object['productRefGroup']]

swift = add('share-swift', isa='PBXFileReference', lastKnownFileType='sourcecode.swift', path='ShareViewController.swift', sourceTree='<group>')
info = add('share-plist', isa='PBXFileReference', lastKnownFileType='text.plist.xml', path='Info.plist', sourceTree='<group>')
entitlements = add('share-entitlements', isa='PBXFileReference', lastKnownFileType='text.plist.entitlements', path='ShareExtension.entitlements', sourceTree='<group>')
share_group = add('share-group', isa='PBXGroup', path='ShareExtension', children=[swift, info, entitlements], sourceTree='<group>')
append_unique(root_group['children'], share_group)
product = add('share-product', isa='PBXFileReference', explicitFileType='wrapper.app-extension', includeInIndex='0', path='ShareExtension.appex', sourceTree='BUILT_PRODUCTS_DIR')
append_unique(products['children'], product)
swift_build = add('share-swift-build', isa='PBXBuildFile', fileRef=swift)
sources = add('share-sources', isa='PBXSourcesBuildPhase', buildActionMask='2147483647', files=[swift_build], runOnlyForDeploymentPostprocessing='0')
frameworks = add('share-frameworks', isa='PBXFrameworksBuildPhase', buildActionMask='2147483647', files=[], runOnlyForDeploymentPostprocessing='0')
resources = add('share-resources', isa='PBXResourcesBuildPhase', buildActionMask='2147483647', files=[], runOnlyForDeploymentPostprocessing='0')
configs = []
for name in ('Debug', 'Release', 'Profile'):
    configs.append(add('share-config-' + name, isa='XCBuildConfiguration', name=name, buildSettings={
        'APPLICATION_EXTENSION_API_ONLY': 'YES', 'CODE_SIGN_STYLE': 'Automatic',
        'CODE_SIGN_ENTITLEMENTS': 'ShareExtension/ShareExtension.entitlements', 'CUSTOM_GROUP_ID': GROUP,
        'CURRENT_PROJECT_VERSION': '1', 'MARKETING_VERSION': '0.1.0',
        'GENERATE_INFOPLIST_FILE': 'NO', 'INFOPLIST_FILE': 'ShareExtension/Info.plist',
        'IPHONEOS_DEPLOYMENT_TARGET': '15.5', 'SWIFT_VERSION': '5.0', 'TARGETED_DEVICE_FAMILY': '1,2',
        'PRODUCT_BUNDLE_IDENTIFIER': APP_ID + '.ShareExtension', 'PRODUCT_NAME': '$(TARGET_NAME)',
        'SKIP_INSTALL': 'YES', 'ALWAYS_EMBED_SWIFT_STANDARD_LIBRARIES': 'NO',
        'LD_RUNPATH_SEARCH_PATHS': ['$(inherited)', '@executable_path/Frameworks', '@executable_path/../../Frameworks'],
    }))
config_list = add('share-config-list', isa='XCConfigurationList', buildConfigurations=configs, defaultConfigurationIsVisible='0', defaultConfigurationName='Release')
target = add('share-target', isa='PBXNativeTarget', name='ShareExtension', productName='ShareExtension',
             productReference=product, productType='com.apple.product-type.app-extension',
             buildConfigurationList=config_list, buildPhases=[sources, frameworks, resources], buildRules=[], dependencies=[])
append_unique(project_object['targets'], target)
proxy = add('share-proxy', isa='PBXContainerItemProxy', containerPortal=project['rootObject'], proxyType='1', remoteGlobalIDString=target, remoteInfo='ShareExtension')
dependency = add('share-dependency', isa='PBXTargetDependency', target=target, targetProxy=proxy)
append_unique(native['dependencies'], dependency)
embedded = add('share-embedded', isa='PBXBuildFile', fileRef=product, settings={'ATTRIBUTES': ['RemoveHeadersOnCopy']})
embed_phase = add('share-embed-phase', isa='PBXCopyFilesBuildPhase', buildActionMask='2147483647', dstPath='', dstSubfolderSpec='13', files=[embedded], name='Embed App Extensions', runOnlyForDeploymentPostprocessing='0')
if embed_phase not in native['buildPhases']:
    native['buildPhases'].insert(-1, embed_phase)
attributes = project_object['attributes'].setdefault('TargetAttributes', {})
for key in (target, next(k for k, v in objects.items() if v is native)):
    attributes.setdefault(key, {})['SystemCapabilities'] = {'com.apple.ApplicationGroups.iOS': {'enabled': '1'}}
for value in objects.values():
    if value.get('isa') == 'XCBuildConfiguration':
        settings = value['buildSettings']
        if 'IPHONEOS_DEPLOYMENT_TARGET' in settings:
            settings['IPHONEOS_DEPLOYMENT_TARGET'] = '15.5'
        bundle = settings.get('PRODUCT_BUNDLE_IDENTIFIER', '')
        if bundle.startswith('dev.formatfactory.formatFactoryMobile'):
            settings['PRODUCT_BUNDLE_IDENTIFIER'] = bundle.replace('dev.formatfactory.formatFactoryMobile', APP_ID)
        if settings.get('INFOPLIST_FILE') == 'Runner/Info.plist':
            settings['CODE_SIGN_ENTITLEMENTS'] = 'Runner/Runner.entitlements'
            settings['CUSTOM_GROUP_ID'] = GROUP

def encode(value, level=0):
    indent = '\t' * level
    if isinstance(value, dict):
        return '{\n' + ''.join('\t' * (level + 1) + json.dumps(k) + ' = ' + encode(v, level + 1) + ';\n' for k, v in value.items()) + indent + '}'
    if isinstance(value, list):
        return '(\n' + ''.join('\t' * (level + 1) + encode(v, level + 1) + ',\n' for v in value) + indent + ')'
    return json.dumps(str(value), ensure_ascii=False)
project_path.write_text('// !$*UTF8*$!\n' + encode(project) + '\n', encoding='utf-8')

scheme = IOS / 'Runner.xcodeproj/xcshareddata/xcschemes/Runner.xcscheme'
tree = ET.parse(scheme)
build_action = tree.getroot().find('BuildAction')
if (pre := build_action.find('PreActions')) is not None:
    build_action.remove(pre)
tree.write(scheme, encoding='utf-8', xml_declaration=True)
for mode in ('Debug', 'Release'):
    (IOS / f'Flutter/{mode}.xcconfig').write_text(f'#include? "Pods/Target Support Files/Pods-Runner/Pods-Runner.{mode.lower()}.xcconfig"\n#include "Generated.xcconfig"\n', encoding='utf-8')

android_build = MOBILE / 'android/app/build.gradle.kts'
android_build.write_text(re.sub(r'applicationId = "[^"]+"', f'applicationId = "{APP_ID}"', android_build.read_text(encoding='utf-8')), encoding='utf-8')
image = Image.open(MOBILE / 'assets/appmark.png').convert('RGBA')
opaque = Image.new('RGBA', image.size, 'white')
opaque.alpha_composite(image)
opaque = opaque.convert('RGB')
for density, size in [('mdpi', 48), ('hdpi', 72), ('xhdpi', 96), ('xxhdpi', 144), ('xxxhdpi', 192)]:
    opaque.resize((size, size), Image.Resampling.LANCZOS).save(MOBILE / f'android/app/src/main/res/mipmap-{density}/ic_launcher.png')
icons = IOS / 'Runner/Assets.xcassets/AppIcon.appiconset'
for entry in json.loads((icons / 'Contents.json').read_text())['images']:
    if name := entry.get('filename'):
        size = round(float(entry['size'].split('x')[0]) * float(entry['scale'].rstrip('x')))
        opaque.resize((size, size), Image.Resampling.LANCZOS).save(icons / name)
print('Configured native identities, icons, iOS permissions and ShareExtension target.')
