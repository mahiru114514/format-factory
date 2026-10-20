"""Native-source integrity checks; this does not claim an iOS compilation."""
import json
from pathlib import Path
import plistlib
import re
from xml.etree import ElementTree as ET
from openstep_parser import OpenStepDecoder
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
mobile = ROOT / 'mobile'
ios = mobile / 'ios'
project = OpenStepDecoder.ParseFromString((ios / 'Runner.xcodeproj/project.pbxproj').read_text(encoding='utf-8'))
objects = project['objects']
targets = {v['name']: v for v in objects.values() if v.get('isa') == 'PBXNativeTarget'}
assert {'Runner', 'RunnerTests', 'ShareExtension'} <= targets.keys()
for key, value in objects.items():
    for field in ('fileRef', 'target', 'targetProxy', 'containerPortal', 'buildConfigurationList', 'mainGroup', 'productRefGroup', 'productReference'):
        if reference := value.get(field):
            assert reference in objects, (key, field, reference)
    for field in ('children', 'buildPhases', 'buildConfigurations', 'dependencies', 'files', 'targets'):
        for reference in value.get(field, []):
            assert reference in objects, (key, field, reference)
assert 'FlutterGeneratedPluginSwiftPackage' not in str(project)
runner = targets['Runner']
share = targets['ShareExtension']
share_id = next(k for k, v in objects.items() if v is share)
assert any(objects[d]['target'] == share_id for d in runner['dependencies'])
assert any(objects[p].get('dstSubfolderSpec') == '13' for p in runner['buildPhases'])
for target in (runner, share):
    configurations = objects[target['buildConfigurationList']]['buildConfigurations']
    for configuration in configurations:
        settings = objects[configuration]['buildSettings']
        assert settings['CUSTOM_GROUP_ID'] == 'group.dev.formatfactory.mobile'
        assert (ios / settings['CODE_SIGN_ENTITLEMENTS']).is_file()
        assert (ios / settings['INFOPLIST_FILE']).is_file()
        bundle = settings['PRODUCT_BUNDLE_IDENTIFIER']
        assert re.fullmatch(r'[A-Za-z0-9.-]+', bundle)
info = plistlib.loads((ios / 'Runner/Info.plist').read_bytes())
assert info['CFBundleDisplayName'] == '格式转换工厂'
for key in ('NSPhotoLibraryUsageDescription', 'NSPhotoLibraryAddUsageDescription', 'NSCameraUsageDescription', 'NSLocalNetworkUsageDescription'):
    assert info[key]
assert 'NSAllowsArbitraryLoads' not in info['NSAppTransportSecurity']
extension = plistlib.loads((ios / 'ShareExtension/Info.plist').read_bytes())
assert extension['NSExtension']['NSExtensionPrincipalClass'].endswith('.ShareViewController')
assert extension['NSExtension']['NSExtensionAttributes']['NSExtensionActivationRule'] != 'TRUEPREDICATE'
for filename in ('Runner/Runner.entitlements', 'ShareExtension/ShareExtension.entitlements'):
    assert plistlib.loads((ios / filename).read_bytes())['com.apple.security.application-groups'] == ['$(CUSTOM_GROUP_ID)']
icons = ios / 'Runner/Assets.xcassets/AppIcon.appiconset'
for entry in json.loads((icons / 'Contents.json').read_text())['images']:
    if filename := entry.get('filename'):
        with Image.open(icons / filename) as icon:
            size = round(float(entry['size'].split('x')[0]) * float(entry['scale'].rstrip('x')))
            assert icon.size == (size, size)
            assert icon.mode == 'RGB', 'iOS app icons must be opaque'
android = ET.parse(mobile / 'android/app/src/main/AndroidManifest.xml').getroot()
namespace = '{http://schemas.android.com/apk/res/android}'
assert any(p.get(namespace + 'name') == 'android.permission.INTERNET' for p in android.findall('uses-permission'))
activity = android.find('application/activity')
actions = {a.get(namespace + 'name') for a in activity.findall('intent-filter/action')}
assert {'android.intent.action.SEND', 'android.intent.action.SEND_MULTIPLE', 'android.intent.action.VIEW'} <= actions
print('Native source integrity checks passed. iOS compilation/device tests still require macOS/Xcode.')
