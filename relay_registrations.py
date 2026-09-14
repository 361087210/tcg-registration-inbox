#!/usr/bin/env python3
# ============================================================
# 网页端注册申请转投飞书 (V10.17.0)
# 由 tcg-registration-inbox 仓库 relay.yml 工作流调用:
#   registrations/pending_reg_*.json → 飞书「APP数据备份/注册申请/」
#   上传成功后删除本仓库源文件(下次运行不重复转投)
# ============================================================
import base64, json, os, sys, time
import urllib.request, urllib.error

APP_ID = os.environ.get('FEISHU_APP_ID', '')
APP_SECRET = os.environ.get('FEISHU_APP_SECRET', '')
ROOT_TOKEN = os.environ.get('FEISHU_FOLDER_TOKEN', '')
GH_TOKEN = os.environ.get('GH_TOKEN', '')
REPO = os.environ.get('GITHUB_REPOSITORY', '361087210/tcg-registration-inbox')

JSON_HEADERS = {'Content-Type': 'application/json'}


def http_json(url, method='GET', data=None, headers=None, timeout=30):
    body = json.dumps(data).encode() if data is not None else None
    h = dict(JSON_HEADERS)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {'code': e.code, 'msg': str(e)}


def gh_api(url, method='GET', data=None):
    body = json.dumps(data).encode() if data is not None else None
    h = {'Authorization': f'Bearer {GH_TOKEN}', 'Accept': 'application/vnd.github+json',
         'Content-Type': 'application/json'}
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def feishu_list_dir(folder_token):
    out, page_token = [], ''
    while True:
        url = (f'https://open.feishu.cn/open-apis/drive/v1/files'
               f'?folder_token={folder_token}&page_size=200')
        if page_token:
            url += f'&page_token={page_token}'
        r = http_json(url)
        if r.get('code') != 0:
            break
        data = r.get('data') or {}
        out.extend(data.get('files') or [])
        page_token = data.get('next_page_token') or ''
        if not page_token:
            break
    return out


def feishu_find_sub(folder_token, name):
    for f in feishu_list_dir(folder_token):
        if f.get('name') == name:
            return f.get('token')
    return None


def feishu_ensure_sub(folder_token, name):
    token = feishu_find_sub(folder_token, name)
    if token:
        return token
    r = http_json('https://open.feishu.cn/open-apis/drive/v1/files/create_folder',
                  'POST', {'name': name, 'folder_token': folder_token})
    return ((r.get('data') or {}).get('token')) if r.get('code') == 0 else None


def feishu_upload_json(folder_token, file_name, text):
    boundary = 'tcgreg' + str(int(time.time() * 1000))
    file_bytes = text.encode('utf-8')
    parts = []
    for field, value in [('file_name', file_name), ('parent_type', 'explorer'),
                         ('parent_node', folder_token), ('size', str(len(file_bytes)))]:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'.encode())
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
                  f'Content-Type: application/json\r\n\r\n').encode())
    parts.append(file_bytes)
    parts.append(f'\r\n--{boundary}--\r\n'.encode())
    body = b''.join(parts)
    req = urllib.request.Request(
        'https://open.feishu.cn/open-apis/drive/v1/files/upload_all',
        data=body,
        headers={'Authorization': 'Bearer ' + _token,
                 'Content-Type': f'multipart/form-data; boundary={boundary}'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {'code': e.code, 'msg': str(e)}


_token = ''


def main():
    global _token
    # ---- 飞书认证 ----
    tok = http_json('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                    'POST', {'app_id': APP_ID, 'app_secret': APP_SECRET})
    if tok.get('code') != 0 or not tok.get('tenant_access_token'):
        print(f"::error::飞书token获取失败: {tok.get('code')} {tok.get('msg')}")
        sys.exit(1)
    _token = tok['tenant_access_token']
    auth = {'Authorization': 'Bearer ' + _token}

    # ---- 定位 注册申请 目录(不存在则创建) ----
    data_folder = feishu_find_sub(ROOT_TOKEN, 'APP数据备份') or feishu_ensure_sub(ROOT_TOKEN, 'APP数据备份')
    if not data_folder:
        print('::error::APP数据备份目录不可用')
        sys.exit(1)
    pending_folder = feishu_ensure_sub(data_folder, '注册申请')
    if not pending_folder:
        print('::error::注册申请目录不可用')
        sys.exit(1)

    # ---- 扫描本仓库 registrations/ 目录 ----
    regs_dir = 'registrations'
    if not os.path.isdir(regs_dir):
        print('registrations/ 目录不存在,无待转投申请')
        return
    names = sorted(n for n in os.listdir(regs_dir) if n.startswith('pending_reg_') and n.endswith('.json'))
    if not names:
        print('无待转投申请')
        return
    print(f'待转投申请 {len(names)} 个: {names}')

    ok_count, fail_count = 0, 0
    for name in names:
        path = os.path.join(regs_dir, name)
        with open(path, 'rb') as f:
            text = f.read().decode('utf-8')
        try:
            json.loads(text)  # 合法性预检
        except Exception as e:
            print(f'::warning::{name} JSON非法,跳过: {e}')
            fail_count += 1
            continue
        up = feishu_upload_json(pending_folder, name, text)
        if up.get('code') == 0:
            print(f'✅ 已转投 {name}')
            ok_count += 1
            # 删除本仓库中的源文件(转投成功才删)
            s, d = gh_api(f'https://api.github.com/repos/{REPO}/contents/{path}')
            if s == 200 and d.get('sha'):
                ds, dd = gh_api(f'https://api.github.com/repos/{REPO}/contents/{path}', 'DELETE',
                                {'message': f'relay: 已转投 {name}', 'sha': d['sha']})
                print(f'   删除源文件: HTTP {ds}')
            else:
                print(f'   ⚠️ 读取源文件sha失败: HTTP {s}')
        else:
            print(f"::warning::{name} 飞书上传失败: code={up.get('code')} msg={up.get('msg')}")
            fail_count += 1
    print(f'转投完成: 成功{ok_count} 失败{fail_count}')
    if fail_count:
        sys.exit(1)  # 非零退出提醒运维;已成功文件已删除不会重复转投


if __name__ == '__main__':
    main()
