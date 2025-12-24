import sys, os, json, qrcode, time, pyncm, requests, re, platform, subprocess, shutil # pyright: ignore[reportMissingModuleSource, reportMissingImports]
from pyncm.apis import playlist, track, login # pyright: ignore[reportMissingImports]
import functools 
import unicodedata
import threading
from contextlib import suppress
from requests.exceptions import Timeout, ConnectionError, RequestException # type: ignore
import time
DEBUG = False
try:
    from colorama import init, Fore, Back, Style # type: ignore
    init(autoreset=False)
    COLORAMA_INSTALLED = True
except ImportError as e:
    if DEBUG: print(e)
    COLORAMA_INSTALLED = False
import mutagen # pyright: ignore[reportMissingImports]
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TRCK, TDRC # pyright: ignore[reportMissingImports]
from mutagen.flac import FLAC, Picture # pyright: ignore[reportMissingImports]
from mutagen import File as MutagenFile # pyright: ignore[reportMissingImports]
from PIL import Image # pyright: ignore[reportMissingImports]
from io import BytesIO
MUTAGEN_INSTALLED = True
USER_INFO_CACHE = {'nickname': None, 'user_id': None, 'vip': None}


def send_notification(title: str, message: str, timeout: int = 5):
    """发通知"""
    with suppress(Exception):
        from plyer import notification  # type: ignore
        with suppress(Exception):
            notification.notify(title=title, message=message, app_name='NCM-Playlist-Downloader', timeout=timeout)
            return
    system = platform.system()
    with suppress(Exception):
        if system == 'Darwin':
            # 使用 AppleScript 显示通知
            safe_title = title.replace('"', '\\"')
            safe_msg = message.replace('"', '\\"')
            subprocess.run(['osascript', '-e', f'display notification "{safe_msg}" with title "{safe_title}"'], check=False)
            return
        elif system == 'Linux':
            if shutil.which('notify-send'):
                subprocess.run(['notify-send', title, message], check=False)
                return
            elif shutil.which('zenity'):
                subprocess.run(['zenity', '--notification', '--text', message, '--title', title], check=False)
                return
            elif shutil.which('kdialog'):
                subprocess.run(['kdialog', '--passivepopup', message, str(timeout), '--title', title], check=False)
                return
            elif shutil.which('termux-notification'):
                subprocess.run(['termux-notification', '--title', title, '--content', message], check=False)
                return
        elif system == 'Windows':
            # Avoid using backslashes inside f-string expressions (Python 3.8 limitation).
            # Precompute escaped title/message, then use simple variable expressions in the f-string.
            safe_title = title.replace('"', '\\"')
            safe_msg = message.replace('"', '\\"')
            ps = f"""
$title = \"{safe_title}\"
$text = \"{safe_msg}\"
[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null
[reflection.assembly]::loadwithpartialname('System.Drawing') | Out-Null
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.BalloonTipTitle = $title
$n.BalloonTipText = $text
$n.Visible = $true
$n.ShowBalloonTip({int(timeout * 1000)})
Start-Sleep -Seconds {max(1, int(timeout))}
$n.Dispose()
"""
            with suppress(Exception):
                subprocess.Popen(['powershell', '-NoProfile', '-Command', ps], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return


def get_clipboard_text():
    """优先尝试 pyperclip，再降级到平台命令获取剪贴板内容，失败返回空字符串。"""
    with suppress(Exception):
        import pyperclip # type: ignore
        with suppress(Exception):
            txt = pyperclip.paste()
            if txt:
                return txt
    with suppress(Exception):
        if shutil.which('termux-clipboard-get'):
            with suppress(Exception):
                p = subprocess.run(['termux-clipboard-get'], capture_output=True, text=True, check=False)
                if p.returncode == 0 and p.stdout:
                    return p.stdout.strip()
        if platform.system() == 'Windows':
            for exe in ('pwsh', 'powershell'):
                with suppress(Exception):
                    p = subprocess.run([exe, '-NoProfile', '-Command', 'Get-Clipboard'], capture_output=True, text=True, check=False)
                    if p.returncode == 0 and p.stdout:
                        return p.stdout.strip()
        elif platform.system() == 'Darwin':
            p = subprocess.run(['pbpaste'], capture_output=True, text=True, check=False)
            if p.returncode == 0:
                return p.stdout.strip()
        else:
            if shutil.which('xclip'):
                p = subprocess.run(['xclip', '-selection', 'clipboard', '-o'], capture_output=True, text=True, check=False)
                if p.returncode == 0:
                    return p.stdout.strip()
            if shutil.which('xsel'):
                p = subprocess.run(['xsel', '--clipboard', '--output'], capture_output=True, text=True, check=False)
                if p.returncode == 0:
                    return p.stdout.strip()
    return ''

def get_terminal_size():
    try:
        columns, lines = shutil.get_terminal_size()
        return (columns, lines)
    except shutil.Error:
        try:
            size = os.get_terminal_size()
            return (size.columns, size.lines)
        except (AttributeError, ImportError):
            raise
    except (AttributeError, ImportError, OSError): 
        try:
            if platform.system() != 'Windows':
                import fcntl, termios, struct
                fd = sys.stdin.fileno()
                hw = struct.unpack('hh', fcntl.ioctl(fd, termios.TIOCGWINSZ, '1234')) # pyright: ignore[reportAttributeAccessIssue]
                return (hw[1], hw[0])
            else:
                from ctypes import windll, create_string_buffer
                h = windll.kernel32.GetStdHandle(-12)
                buf = create_string_buffer(22)
                windll.kernel32.GetConsoleScreenBufferInfo(h, buf)
                left, top, right, bottom = struct.unpack('hhhhHhhhhhh', buf.raw)[5:9] # pyright: ignore[reportAttributeAccessIssue, reportUnboundVariable]
                return (right - left + 1, bottom - top + 1)
        except:
            return (80, 24)

def retry_with_timeout(timeout=30, retry_times=2, operation_name='操作'):
    """通用超时重试装饰器"""

    def decorator(func):

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            last_error = None
            while retries <= retry_times:
                try:
                    result = func(*args, **kwargs)
                    return (result, None)
                except (Timeout, ConnectionError, RequestException) as e:
                    retries += 1
                    last_error = e
                    if retries <= retry_times:
                        print(f'\x1b[33m! {operation_name}超时，正在重试 ({retries}/{retry_times})...\x1b[0m\x1b[K')
                    else:
                        print(f'\x1b[31m× {operation_name}多次超时，放弃尝试。\x1b[0m\x1b[K')
                        break
            return (None, last_error)
        return wrapper
    return decorator

def get_qrcode():
    """
    提供三种登录方式选择：
    1) pyncm 直接扫码（复用原实现）
    2) 打开浏览器扫码登录（占位，未实现）
    3) 手机短信/账号密码登录
    返回已登录的 session 或 None。
    """
    try:
        print('\n  请选择登录方式：')
        print('  \x1b[36m[1]\x1b[0m \x1b[1mpyncm 直接扫码登录\x1b[0m \t\x1b[2m手机端扫描二维码登录\x1b[0m')
        print('  \x1b[36m[2]\x1b[0m 打开浏览器扫码登录\x1b[0m \t\x1b[2m适用于桌面设备，需要外部浏览器\x1b[0m')
        print('  \x1b[36m[3]\x1b[0m 手机短信/账号密码登录 \t\x1b[2m本地终端实现\x1b[0m')
        print('  \x1b[36m[4]\x1b[0m 手动导入 Cookie 登录 \t\x1b[2m直接粘贴 MUSIC_U 等 cookie 字串\x1b[0m')
        print('  \x1b[36m[5]\x1b[0m 匿名登录 \t\t\t\x1b[2m创建随机凭据，不推荐\x1b[0m')
        gm_cookie_path = None
        try:
            candidates = []
            mf_root = os.environ.get('MUSICFOX_ROOT')
            if mf_root:
                candidates.append(os.path.join(mf_root, 'cookie'))

            system = platform.system()
            home = os.path.expanduser('~')
            if DEBUG: print(f'system: {system}, home: {home}')
            if system == 'Darwin':
                candidates.append(os.path.join(home, 'Library', 'Application Support', 'go-musicfox', 'cookie'))
                candidates.append(os.path.join(home, '.go-musicfox', 'cookie'))
            elif system == 'Linux':
                xdg = os.environ.get('XDG_CONFIG_HOME')
                if xdg:
                    candidates.append(os.path.join(xdg, 'go-musicfox', 'cookie'))
                candidates.append(os.path.join(home, '.local', 'share', 'go-musicfox', 'cookie'))
                candidates.append(os.path.join(home, '.go-musicfox', 'cookie'))
            elif system == 'Windows':
                appdata = os.environ.get('APPDATA')
                if appdata:
                    candidates.append(os.path.join(appdata, 'go-musicfox', 'cookie'))
                local_appdata = os.environ.get('LOCALAPPDATA')
                if local_appdata:
                    candidates.append(os.path.join(local_appdata, 'go-musicfox', 'cookie'))
                userprofile = os.environ.get('USERPROFILE') or home
                candidates.append(os.path.join(userprofile, '.go-musicfox', 'cookie'))
            else:
                xdg = os.environ.get('XDG_CONFIG_HOME')
                if xdg:
                    candidates.append(os.path.join(xdg, 'go-musicfox', 'cookie'))
                candidates.append(os.path.join(home, '.local', 'share', 'go-musicfox', 'cookie'))
                candidates.append(os.path.join(home, '.go-musicfox', 'cookie'))

            if system == 'Windows' and not os.environ.get('LOCALAPPDATA'):
                local_guess = os.path.join(home, 'AppData', 'Local', 'go-musicfox', 'cookie')
                candidates.append(local_guess)

            for p in candidates:
                with suppress(Exception):
                    if DEBUG: print(p)
                    if p and os.path.exists(p):
                        gm_cookie_path = p
                        if DEBUG: print(f'SUCCESS: added entry(see below) gm_cookie_path:{gm_cookie_path}, ')
                        break
                    if DEBUG: print("^"*len(p) + " -> NOT EXIST")
        except Exception:
            gm_cookie_path = None
        gm_exists = bool(gm_cookie_path and os.path.exists(gm_cookie_path))
        if gm_exists:
            print(f"  \x1b[32m[6]\x1b[0m 通过 go-musicfox 登录\t\x1b[2m您已在 musicfox 中登录，可直接使用\x1b[0m")
        choice = input('  请选择 (默认 1)\x1b[36m > \x1b[0m').strip() or '1'
        if choice == '1':
            try:
                # print('\x1b[33m! 使用 pyncm 直接扫码登录已确认因接口过时封堵，您仍要尝试吗？\x1b[0m')
                # print('  [0] 取消  [9] 继续')
                # confirm = input('  请输入您的选择 > ').strip()
                # if confirm == '9':
                #     print('\x1b[33m! 正在尝试 pyncm 直接扫码登录...\x1b[0m')
                # else:
                #     print('\x1b[31m× 已取消 pyncm 直接扫码登录。\x1b[0m')
                #     return get_qrcode()
                uuid_rsp = login.LoginQrcodeUnikey()
                uuid = uuid_rsp.get('unikey') if isinstance(uuid_rsp, dict) else None
                if not uuid:
                    print('\x1b[31m× 无法获取二维码unikey\x1b[0m\x1b[K')
                    return get_qrcode()
                # url = f'https://music.163.com/login?codekey={uuid}'
                url = login.GetLoginQRCodeUrl(uuid)
                img = qrcode.make(url)
                img_path = 'ncm.png'
                img.save(img_path) # pyright: ignore[reportArgumentType]
                print("\x1b[32m✓ \x1b[0m二维码已保存为 'ncm.png'，请使用网易云音乐APP扫码登录。")
                try:
                    open_image(img_path)
                except Exception as e:
                    print(f'{e}，请手动打开 ncm.png 文件进行扫码登录')
                __802_displayed = False
                max_polls = 180
                for attempt in range(max_polls):
                    try:
                        rsp = login.LoginQrcodeCheck(uuid)
                        if DEBUG:
                            print(f'DEBUG: 二维码检查响应: {rsp}')
                        code = rsp.get('code') if isinstance(rsp, dict) else None
                        if code == 803:
                            session = pyncm.GetCurrentSession()
                            with suppress(Exception):
                                login.WriteLoginInfo(login.GetCurrentLoginStatus(), session)
                            print('\x1b[32m✓ \x1b[0m登录成功')
                            with suppress(Exception):
                                display_user_info(session)
                            return session
                        elif code == 8821:
                            print('\x1b[33m! 接口风控(8821)\x1b[0m\x1b[K')
                            raise RuntimeError('登录二维码接口已失效')
                        elif code == 800:
                            print('  二维码已过期，请重新尝试。')
                            break
                        elif code == 802:
                            if not __802_displayed:
                                send_notification('扫码登录', '扫码成功，请在手机端确认登录。')
                                print(f'\x1b[33m  用户扫码成功，请在手机端确认登录。\x1b[0m\x1b[K')
                                __802_displayed = True
                        elif code != 801:
                            msg = rsp.get('message') if isinstance(rsp, dict) else None
                            print(f'\x1b[31m× 二维码检查失败，出现未知错误: {msg}\x1b[0m\x1b[K')
                        time.sleep(1)
                    except (Timeout, ConnectionError, RequestException) as e:
                        print(f'\x1b[33m! 二维码检查遇到网络错误: {e}，正在重试...\x1b[0m\x1b[K')
                        time.sleep(1)
                        continue
                print('\x1b[31m× 二维码登录超时或已过期\x1b[0m\x1b[K')
                return get_qrcode()
            except Exception as e:
                print(f'\x1b[31m× 验证出错: {e}\x1b[0m\x1b[K')
                raise
        elif choice == '2':
            '\n            加载 https://music.163.com/#/login, 在用户扫码登录后获取 cookie 并关闭窗口.\n\n            监测 cookie 的添加, 经实验可知在 https://music.163.com/#/login 登陆后会自动跳转到 https://music.163.com/#/discover, 并且监测 url 的变化, 所以实际上可以先记录所有添加的 cookie, 然后在 url 变化的时候返回所有被记录的 cookie 并关闭窗口(可以直接将 cookie 注入一个新的 session, 然后返回这个 session )\n            '
            print('\x1b[33m! 打开浏览器扫码登录，请在提示"正由自动测试软件控制"的浏览器窗口扫码登录。\x1b[0m')
            try:
                session = browser_qr_login_via_selenium()
                if session:
                    pyncm.SetCurrentSession(session)
                    with suppress(Exception):
                        login.WriteLoginInfo(login.GetCurrentLoginStatus(), session)
                    print(f'\x1b[32m✓ \x1b[0m浏览器登录成功')
                    with suppress(Exception):
                        display_user_info(session)
                    return session
                else:
                    print('\x1b[31m× 浏览器登录失败或超时\x1b[0m')
                    return get_qrcode()
            except ImportError:
                print('\x1b[31m× 未安装 selenium，请先安装: pip install selenium\x1b[0m')
                return get_qrcode()
            except Exception as e:
                print(f'\x1b[31m× 浏览器登录出错: {e}\x1b[0m')
                return get_qrcode()
        elif choice == '3':
            '\n            参考 手机登录测试.py，实现两种方式：\n            - 短信验证码登录\n            - 账号（手机）+密码登录\n            '
            print('\x1b[33m! 手机短信/账号密码登录。\x1b[0m')
            try:
                ct_inp = input('  请输入国家代码(默认 86) > ').strip()
                phone = input('  请输入手机号 > ').strip()
                try:
                    ctcode = int(ct_inp) if ct_inp else 86
                except Exception:
                    ctcode = 86
                print('  选择登录方式：\n  [1] 短信验证码\n  [2] 账号密码')
                m = input('  请选择 (默认 1) > ').strip() or '1'
                if m == '2':
                    try:
                        import getpass
                        try:
                            password = getpass.getpass('  输入密码 > ', echo_char='*')
                        except TypeError:
                            password = getpass.getpass('  输入密码 > ')
                    except Exception as e:
                        if DEBUG: print(e.__class__, e)
                        password = input('  输入密码 > ')
                    rsp = login.LoginViaCellphone(phone, password=password, ctcode=ctcode)
                    code = rsp.get('code') if isinstance(rsp, dict) else None
                    if code == 200:
                        session = pyncm.GetCurrentSession()
                        with suppress(Exception):
                            login.WriteLoginInfo(login.GetCurrentLoginStatus(), session)
                        print('\x1b[32m✓ \x1b[0m登录成功（密码）')
                        with suppress(Exception):
                            display_user_info(session)
                        return session
                    else:
                        msg = rsp.get('message') if isinstance(rsp, dict) else None
                        print(f'\x1b[31m× 登录失败: {msg}\x1b[0m')
                        return get_qrcode()
                else:
                    send_rsp = login.SetSendRegisterVerifcationCodeViaCellphone(phone, ctcode)
                    scode = send_rsp.get('code') if isinstance(send_rsp, dict) else None
                    if scode != 200:
                        print(f'\x1b[31m× 发送验证码失败: {send_rsp}\x1b[0m')
                        return get_qrcode()
                    print('\x1b[32m✓ \x1b[0m已发送验证码，请查收短信。')
                    while True:
                        captcha = input('  输入短信验证码 > ').strip()
                        if not captcha:
                            print('\x1b[33m! 验证码不能为空\x1b[0m')
                            continue
                        v = login.GetRegisterVerifcationStatusViaCellphone(phone, captcha, ctcode)
                        vcode = v.get('code') if isinstance(v, dict) else None
                        if vcode == 200:
                            print('\x1b[32m✓ \x1b[0m验证成功')
                            break
                        else:
                            print(f'\x1b[33m! 验证失败，请重试。响应: {v}\x1b[0m')
                    rsp = login.LoginViaCellphone(phone, captcha=captcha, ctcode=ctcode)
                    code = rsp.get('code') if isinstance(rsp, dict) else None
                    if code == 200:
                        session = pyncm.GetCurrentSession()
                        with suppress(Exception):
                            login.WriteLoginInfo(login.GetCurrentLoginStatus(), session)
                        print('\x1b[32m✓ \x1b[0m登录成功（短信）')
                        with suppress(Exception):
                            display_user_info(session)
                        return session
                    else:
                        msg = rsp.get('message') if isinstance(rsp, dict) else None
                        print(f'\x1b[31m× 登录失败: {msg}\x1b[0m')
                        return get_qrcode()
            except Exception as e:
                print(f'\x1b[31m× 手机登录出错: {e}\x1b[0m')
                return get_qrcode()
        elif choice == '5':
            print('\x1b[33m! 尝试创建随机凭据登录。\x1b[0m')
            try:
                rsp = login.LoginViaAnonymousAccount()
                code = None
                nickname = None
                user_id = None
                if isinstance(rsp, dict):
                    content = rsp.get('content') or rsp
                    code = content.get('code') if isinstance(content, dict) else None
                    prof = (content.get('profile') if isinstance(content, dict) else None) or {}
                    nickname = prof.get('nickname') or prof.get('nickName')
                    user_id = content.get('userId') or (prof.get('userId') if isinstance(prof, dict) else None)
                if code == 200:
                    session = pyncm.GetCurrentSession()
                    with suppress(Exception):
                        login.WriteLoginInfo(login.GetCurrentLoginStatus(), session)
                    print(f'\x1b[32m✓ 匿名登录成功\x1b[0m')
                    with suppress(Exception):
                        display_user_info(session)
                    return session
                else:
                    print('\x1b[31m× 匿名登录失败\x1b[0m')
                    return get_qrcode()
            except Exception as e:
                print(f'\x1b[31m× 匿名登录出错: {e}\x1b[0m')
                return get_qrcode()
        elif choice == '6':
            # 读取并导入 %LOCALAPPDATA%\go-musicfox\cookie（Netscape 格式）
            if not gm_exists:
                print('\x1b[33m! 无效选择。\x1b[0m')
                return get_qrcode()
            print('\x1b[33m! 正在从 go-musicfox 获取登录状态...\x1b[0m')
            try:
                cookies = []  # 每项: {domain, path, name, value}
                with open(gm_cookie_path, 'r', encoding='utf-8', errors='ignore') as fh:
                    for raw in fh:
                        line = raw.strip()
                        if not line:
                            continue
                        # 以制表符为主进行切分，不足则尝试任意空白
                        parts = line.split('\t') if ('\t' in line) else line.split()
                        if len(parts) < 7:
                            continue
                        domain = parts[0]
                        if domain.startswith('#HttpOnly_') or domain.startswith('#httponly_'):
                            domain = domain.split('_', 1)[1]
                        if domain.startswith('#'):
                            # 注释行
                            continue
                        path = parts[2]
                        name = parts[5]
                        value = parts[6]
                        if not name:
                            continue
                        cookies.append({'domain': domain, 'path': path or '/', 'name': name, 'value': value})
                if not cookies:
                    print('\x1b[31m× 未能从 go-musicfox Cookie 文件解析到任何条目。\x1b[0m')
                    return get_qrcode()
                # 构建/获取会话并注入 cookie
                try:
                    s = pyncm.GetCurrentSession()
                except Exception as e:
                    if DEBUG: print(e)
                    s = None
                if s is None:
                    try:
                        import requests as _rq
                        s = _rq.Session()
                    except Exception as e:
                        if DEBUG: print(e)
                        s = pyncm.GetCurrentSession()  # 尽力而为
                # 设置通用头
                ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari'
                with suppress(Exception):
                    s.headers.update({'User-Agent': ua, 'Referer': 'https://music.163.com/', 'Origin': 'https://music.163.com'})
                # 注入 cookies
                music_u_found = False
                csrf_val = None
                for c in cookies:
                    name = c['name']
                    value = c['value']
                    domain = c['domain'] or '.music.163.com'
                    path = c['path'] or '/'
                    with suppress(Exception):
                        s.cookies.set(name, value, domain=domain, path=path)
                    if name == 'MUSIC_U' and value:
                        music_u_found = True
                    if name in ('__csrf', 'csrf_token') and value:
                        csrf_val = value
                # 补写 csrf_token（requests 不会自动映射）
                if csrf_val and (not s.cookies.get('csrf_token')):
                    with suppress(Exception):
                        s.cookies.set('csrf_token', csrf_val, domain='.music.163.com', path='/')
                # 挂载为当前会话并写入缓存
                with suppress(Exception):
                    pyncm.SetCurrentSession(s)
                with suppress(Exception):
                    login.WriteLoginInfo(login.GetCurrentLoginStatus(), s)
                print('\x1b[32m✓ go-musicfox 登录完成。\x1b[0m')
                if not music_u_found:
                    print('\x1b[33m! 警告：未检测到 MUSIC_U，登录流程实际失败！\x1b[0m')
                with suppress(Exception):
                    display_user_info(s)
                return s
            except FileNotFoundError:
                print('\x1b[31m× 找不到 go-musicfox Cookie 文件。\x1b[0m')
                return get_qrcode()
            except Exception as e:
                print(f'\x1b[31m× 导入 go-musicfox Cookie 失败: {e}\x1b[0m')
                return get_qrcode()
        elif choice == '4':
            '\n            从剪贴板或手动粘贴 Cookie 登录（会解析 k=v; k2=v2 格式），并注入到 pyncm.Session\n            '
            print('\x1b[33m! 导入外部cookies登录。\x1b[0m')

            def _parse_and_inject(cookie_text):
                if not cookie_text:
                    return (None, 'empty')
                parsed = {}
                try:
                    j = json.loads(cookie_text)
                    if isinstance(j, dict):
                        parsed.update({k: str(v) for k, v in j.items()})
                except Exception:
                    parts = [p.strip() for p in cookie_text.split(';') if '=' in p]
                    for pair in parts:
                        try:
                            k, v = pair.split('=', 1)
                            parsed[k.strip()] = v.strip()
                        except Exception:
                            continue
                if not parsed:
                    return (None, 'noparsed')
                if 'MUSIC_U' not in parsed:
                    return (parsed, 'nomusic_u')
                s = pyncm.GetCurrentSession()
                ua = ''
                try:
                    j = json.loads(cookie_text)
                    ua = j.get('userAgent') or j.get('ua') or ''
                except Exception:
                    ua = ''
                if not ua:
                    ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari'
                s.headers.update({'User-Agent': ua, 'Referer': 'https://music.163.com/', 'Origin': 'https://music.163.com'})
                for name, value in parsed.items():
                    if not name or value is None:
                        continue
                    with suppress(Exception):
                        s.cookies.set(name, value, domain='.music.163.com', path='/')
                if ('__csrf' in parsed or 'csrf_token' in parsed) and (not s.cookies.get('csrf_token')):
                    token = parsed.get('__csrf') or parsed.get('csrf_token')
                    if token:
                        with suppress(Exception):
                            s.cookies.set('csrf_token', token, domain='.music.163.com', path='/')
                with suppress(Exception):
                    login.WriteLoginInfo(login.GetCurrentLoginStatus(), s)
                return (s, 'ok')
            print('\n  您可以直接粘贴 Cookie 字符串，或先将 Cookie 复制到剪贴板后直接回车。\n  若您的浏览器支持导出 Cookies （如 Via），请优先使用该特性\n  否则，请在浏览器开发者工具(F12) - Network（网络） - （除插件外任意请求条目） - Headers（标头） - Request Headers（请求标头） 中找到 Cookie 字段，双击选中复制其值。\n  注意：使用 document.cookie 复制的 Cookie 不包含关键凭据，登录会失败。\n')
            cb = get_clipboard_text() or ''
            cookie_text = cb
            if cookie_text:
                print(f"  检测到剪贴板内容：{cookie_text[:120] + ('...' if len(cookie_text) > 120 else '')}")
                use_cb = input('  使用剪贴板内容作为 Cookie 并登录？[Y/n] > ').strip().lower() or 'y'
                if use_cb not in ('y', 'yes'):
                    cookie_text = ''
            if not cookie_text:
                cookie_text = input('  请输入或粘贴 Cookie 字串 (k=v; k2=v2) > ').strip()
            if not cookie_text:
                cb2 = get_clipboard_text() or ''
                if cb2:
                    print(f"  从剪贴板检测到内容：{cb2[:120] + ('...' if len(cb2) > 120 else '')}")
                    use_cb2 = input('  使用剪贴板内容作为 Cookie 并登录？[Y/n] > ').strip().lower() or 'y'
                    if use_cb2 in ('y', 'yes'):
                        cookie_text = cb2
                    else:
                        cookie_text = ''
                if not cookie_text:
                    cookie_text = input('  未检测到剪贴板内容，请粘贴 Cookie 字串并回车（留空取消）> ').strip()
                    if not cookie_text:
                        print('\x1b[33m! 未提供 Cookie，已取消。\x1b[0m')
                        return get_qrcode()
            sess_or_parsed, status = _parse_and_inject(cookie_text)
            if status == 'empty' or status == 'noparsed':
                print('\x1b[31m× 无法解析 Cookie 字符串，请确保为 k=v; k2=v2 或 JSON 格式。\x1b[0m')
                return get_qrcode()
            if status == 'nomusic_u':
                print('\x1b[33m! 解析到的 Cookie 中未包含 MUSIC_U，登录可能失败。\x1b[0m')
                print('\n  因为MUSIC_U字段使用浏览器 HttpOnly Cookie存储，无法通过 document.cookie 获取。\n  您可以尝试以下方法获取 MUSIC_U：\n  - 使用支持导出完整 Cookie 的浏览器或插件（推荐）\n  - 登录网页版网易云音乐，使用浏览器开发者工具(F12) - Application（应用） - Cookies 中查找 MUSIC_U 并复制其值\n  - 如果您有其他设备已登录网易云音乐，可以尝试从该设备的浏览器中获取 MUSIC_U\n')
                mu = get_clipboard_text().strip() or ''
                if mu and ('MUSIC_U=' in mu or 'MUSIC_U' in mu):
                    m = None
                    try:
                        parts = [p.strip() for p in mu.split(';') if '=' in p]
                        for pair in parts:
                            k, v = pair.split('=', 1)
                            if k.strip() == 'MUSIC_U':
                                m = v.strip()
                                break
                    except Exception:
                        m = None
                    if not m and 'MUSIC_U=' in mu:
                        try:
                            m = mu.split('MUSIC_U=', 1)[1].split(';', 1)[0]
                        except Exception:
                            m = None
                    if m:
                        use_mu = input(f'  检测到剪贴板可能包含 MUSIC_U: {m[:8]}...，使用此值？[Y/n] > ').strip().lower() or 'y'
                        if use_mu in ('y', 'yes'):
                            manual_music_u = m
                        else:
                            manual_music_u = ''
                    else:
                        manual_music_u = ''
                else:
                    manual_music_u = ''
                if not manual_music_u:
                    manual_music_u = input('  未检测到 MUSIC_U，请手动粘贴或输入 MUSIC_U 值（留空取消）> ').strip()
                if not manual_music_u:
                    confirm = input('\x1b[41;97m! 未提供 MUSIC_U，仍要注入其它 Cookie 并尝试登录吗？\r\n  该程序接下来遇到的问题请自行处理，开发者不会受理任何因此操作的错误反馈!\r\n[y/N]\x1b[0m > ').strip().lower() or 'n'
                    if confirm not in ('y', 'yes'):
                        return get_qrcode()
                    parsed = sess_or_parsed if isinstance(sess_or_parsed, dict) else {}
                else:
                    parsed = sess_or_parsed if isinstance(sess_or_parsed, dict) else {}
                    parsed['MUSIC_U'] = manual_music_u
                s = pyncm.GetCurrentSession()
                ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                s.headers.update({'User-Agent': ua, 'Referer': 'https://music.163.com/', 'Origin': 'https://music.163.com'})
                for name, value in parsed.items() if isinstance(parsed, dict) else []:
                    with suppress(Exception):
                        s.cookies.set(name, value, domain='.music.163.com', path='/')
                with suppress(Exception):
                    login.WriteLoginInfo(login.GetCurrentLoginStatus(), s)
                print('\x1b[32m✓ Cookie 会话已创建。\x1b[0m')
                with suppress(Exception):
                    display_user_info(s)
                return s
            session = sess_or_parsed
            if session:
                with suppress(Exception):
                    pyncm.SetCurrentSession(session)
                print('\x1b[32m✓ Cookie 注入成功，会话已创建。\x1b[0m')
                with suppress(Exception):
                    display_user_info(session)
                return session
        else:
            print('\x1b[33m! 无效选择。\x1b[0m')
            return get_qrcode()
    except Exception as e:
        print(f'\x1b[31m× get_qrcode 出现错误: {e}\x1b[0m\x1b[K')
        raise

def browser_qr_login_via_selenium(timeout_seconds: int=180):
    """使用本机浏览器打开网易云登录页，扫码后抓取 Cookie 并构建可用的 pyncm 会话。

    成功条件：
    - 浏览器地址从 #/login 跳转到 #/discover 等页面，或
    - 出现关键登录 Cookie：MUSIC_U

    返回：
    - requests.Session（已注入 cookies 和 headers），失败返回 None
    """
    with suppress(Exception):
        import logging as _logging, os as _os
        _os.environ.setdefault('WDM_LOG_LEVEL', '0')
        _os.environ.setdefault('WDM_PRINT_FIRST_LINE', '0')
        _logging.getLogger('selenium').setLevel(_logging.CRITICAL)
        _logging.getLogger('urllib3').setLevel(_logging.CRITICAL)
        _logging.getLogger('selenium.webdriver.remote').setLevel(_logging.CRITICAL)
    with suppress(Exception):
        import shutil as _shutil, subprocess as _subprocess, json as _json
        is_termux = False
        try:
            if _shutil.which('termux-clipboard-get') or _shutil.which('termux-open-url') or _shutil.which('termux-change-repo') or os.path.exists('/data/data/com.termux'):
                is_termux = True
        except Exception:
            is_termux = False
        if is_termux:
            login_url = 'https://y.music.163.com/m/login'
            print('\x1b[33m! 检测到 Termux/Android 环境，使用 Via 浏览器（mark.via / mark.via.gp）打开登录页\x1b[0m')
            via_candidates = ['mark.via', 'mark.via.gp']
            installed_via = None
            for cand in via_candidates:
                try:
                    p = _subprocess.run(['am', 'start', '-a', 'android.intent.action.VIEW', '-d', login_url, '-p', cand], capture_output=True, text=True, check=False)
                    if p.returncode == 0:
                        installed_via = cand
                        break
                except Exception:
                    continue
            if not installed_via:
                print('\x1b[31m× 未检测到可用的 Via 浏览器 (mark.via / mark.via.gp) 或无法通过包名启动。请先安装 Via 后重试。\x1b[0m')
                print('  可通过 Play 商店或 F-Droid 安装：')
                print('    Play 商店: https://play.google.com/store/apps/details?id=mark.via.gp')
                print('  或直接下载 APK 安装：')
                print('    https://res.viayoo.com/v1/via-release-cn.apk')
                with suppress(Exception):
                    if _shutil.which('termux-open-url'):
                        _subprocess.Popen(['termux-open-url', 'https://res.viayoo.com/v1/via-release-cn.apk'])
                    else:
                        _subprocess.Popen(['am', 'start', '-a', 'android.intent.action.VIEW', '-d', 'https://res.viayoo.com/v1/via-release-cn.apk'])
                
                return None
            try:
                print(f'  将使用 Via ({installed_via}) 打开移动端登录页...')
                _subprocess.Popen(['am', 'start', '-a', 'android.intent.action.VIEW', '-d', login_url, '-p', installed_via])
            except Exception:
                print('\x1b[31m× 无法启动 Via 浏览器， 请确认 Via 已安装并允许从 Termux 启动。\x1b[0m')
                return None
            print('  请在 Via 浏览器中完成登录；\n. 登录成功后请使用右上角图标复制 Cookie 到剪贴板，程序将自动读取（等待最多 %s 秒）...\n. 若程序卡死请检查是否安装Termux:API...' % timeout_seconds)
            start = time.time()
            cookie_text = None
            while time.time() - start < timeout_seconds:
                with suppress(Exception):
                    content = get_clipboard_text() or ''
                    if content and ('MUSIC_U' in content or 'csrf' in content or '__csrf' in content):
                        cookie_text = content
                        break
                
                time.sleep(1)
            if not cookie_text:
                print('  未在剪贴板检测到有效 Cookie，请手动将从浏览器复制的 Cookie 粘贴到这里（长按终端，选择Paste）：')
                cookie_text = input('  粘贴 Cookie 字串并回车 > ').strip()
            if cookie_text:
                try:
                    cookie_pairs = [p.strip() for p in cookie_text.split(';') if '=' in p]
                    parsed = {}
                    for pair in cookie_pairs:
                        k, v = pair.split('=', 1)
                        parsed[k.strip()] = v.strip()
                    if 'MUSIC_U' in parsed:
                        s = pyncm.GetCurrentSession()
                        ua = ''
                        try:
                            j = _json.loads(cookie_text)
                            ua = j.get('userAgent') or j.get('ua') or ''
                        except Exception:
                            ua = ''
                        if not ua:
                            ua = 'Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Mobile'
                        s.headers.update({'User-Agent': ua, 'Referer': 'https://y.music.163.com/', 'Origin': 'https://y.music.163.com'})
                        for name, value in parsed.items():
                            if not name or value is None:
                                continue
                            s.cookies.set(name, value, domain='.music.163.com', path='/')
                        if ('__csrf' in parsed or 'csrf_token' in parsed) and (not s.cookies.get('csrf_token')):
                            token = parsed.get('__csrf') or parsed.get('csrf_token')
                            if token:
                                s.cookies.set('csrf_token', token, domain='.music.163.com', path='/')
                        print('\x1b[32m✓ \x1b[0m已从剪贴板获取到 Cookie，登录成功（Termux）')
                        return s
                    else:
                        print('\x1b[33m! 从剪贴板解析到的 Cookie 中未找到 MUSIC_U，继续回退到桌面/selenium 方案\x1b[0m')
                except Exception as e:
                    print(f'\x1b[33m! 解析剪贴板 Cookie 时出错: {e}\x1b[0m')
            else:
                print('\x1b[33m! 未能在剪贴板中读取到 Cookie，回退到桌面/selenium 方案\x1b[0m')
    try:
        from selenium import webdriver # pyright: ignore[reportMissingImports]
        from selenium.webdriver.chrome.options import Options as ChromeOptions # pyright: ignore[reportMissingImports]
        from selenium.webdriver.edge.options import Options as EdgeOptions # pyright: ignore[reportMissingImports]
        from selenium.webdriver.firefox.options import Options as FirefoxOptions # pyright: ignore[reportMissingImports]
        from selenium.webdriver.common.by import By # pyright: ignore[reportMissingImports]
        from selenium.webdriver.support.ui import WebDriverWait # pyright: ignore[reportMissingImports]
        from selenium.webdriver.support import expected_conditions as EC # pyright: ignore[reportMissingImports]
    except ImportError:
        raise
    driver = None
    last_err = None

    def try_new_driver():
        nonlocal last_err
        import os as _os, subprocess as _subprocess
        try:
            from selenium.webdriver.chrome.service import Service as ChromeService # pyright: ignore[reportMissingImports]
        except Exception:
            ChromeService = None
        try:
            from selenium.webdriver.edge.service import Service as EdgeService # pyright: ignore[reportMissingImports]
        except Exception:
            EdgeService = None
        try:
            from selenium.webdriver.firefox.service import Service as FirefoxService # type: ignore
        except Exception:
            FirefoxService = None
        creationflags = 0
        if platform.system() == 'Windows' and hasattr(_subprocess, 'CREATE_NO_WINDOW'):
            creationflags = _subprocess.CREATE_NO_WINDOW
        with suppress(Exception):
            _os.environ.setdefault('CHROME_LOG_FILE', _os.devnull)
        with suppress(Exception):
            _os.environ.setdefault('MOZ_LOG', '')
        try:
            edge_opts = EdgeOptions()
            edge_opts.add_argument('--disable-gpu')
            edge_opts.add_argument('--start-maximized')
            edge_opts.add_experimental_option('excludeSwitches', ['enable-logging'])
            edge_opts.add_experimental_option('useAutomationExtension', False)
            edge_opts.add_argument('--disable-breakpad')
            edge_opts.add_argument('--disable-dev-shm-usage')
            edge_opts.add_argument('--disable-extensions')
            edge_opts.add_argument('--disable-crash-reporter')
            if EdgeService:
                svc = EdgeService(log_path=_os.devnull, creationflags=creationflags)
                return webdriver.Edge(service=svc, options=edge_opts)
            else:
                return webdriver.Edge(options=edge_opts)
        except Exception as e:
            last_err = e
        try:
            ch_opts = ChromeOptions()
            ch_opts.add_argument('--disable-gpu')
            ch_opts.add_argument('--start-maximized')
            ch_opts.add_experimental_option('excludeSwitches', ['enable-logging'])
            ch_opts.add_experimental_option('useAutomationExtension', False)
            ch_opts.add_argument('--log-level=3')
            ch_opts.add_argument('--disable-extensions')
            ch_opts.add_argument('--disable-breakpad')
            ch_opts.add_argument('--disable-dev-shm-usage')
            ch_opts.add_argument('--disable-crash-reporter')
            ch_opts.add_argument('--disable-software-rasterizer')
            if ChromeService:
                svc = ChromeService(log_path=_os.devnull, creationflags=creationflags)
                return webdriver.Chrome(service=svc, options=ch_opts)
            else:
                return webdriver.Chrome(options=ch_opts)
        except Exception as e:
            last_err = e
        try:
            ff_opts = FirefoxOptions()
            ff_opts.set_preference('dom.webdriver.enabled', True)
            ff_opts.set_preference('log', '{"level": "fatal"}')
            with suppress(Exception):
                firefox_exec = shutil.which('firefox') or '/snap/bin/firefox'
                try:
                    if firefox_exec == '/usr/bin/firefox' and os.path.exists('/usr/bin/firefox'):
                        with open('/usr/bin/firefox', 'rb') as fh:
                            head = fh.read(4)
                        is_script = head.startswith(b'#!') or b'shell' in head.lower()
                    else:
                        is_script = False
                except Exception:
                    is_script = False
                if firefox_exec and (firefox_exec.startswith('/snap') or is_script):
                    snap_candidates = ['/snap/firefox/current/usr/lib/firefox/firefox', '/snap/firefox/current/firefox', '/snap/bin/firefox']
                    for cand in snap_candidates:
                        if os.path.exists(cand) and os.access(cand, os.X_OK):
                            ff_opts.binary_location = cand
                            break
                elif firefox_exec and os.path.exists(firefox_exec):
                    ff_opts.binary_location = firefox_exec
            if FirefoxService:
                svc = FirefoxService(log_path=_os.devnull, service_args=None)
                return webdriver.Firefox(service=svc, options=ff_opts)
            else:
                return webdriver.Firefox(options=ff_opts)
        except Exception as e:
            last_err = e
        return None
    driver = try_new_driver()
    if not driver:
        raise RuntimeError(f'无法启动浏览器: {last_err}')
    login_url = 'https://music.163.com/#/login'
    target_domains = {'music.163.com', '.music.163.com', '.163.com'}
    start = time.time()
    try:
        driver.get(login_url)
        print('  已打开登录页面，请使用手机网易云音乐扫码并确认...')
        logged_in = False
        music_u = None
        csrf = None
        while time.time() - start < timeout_seconds:
            current_url = driver.current_url or ''
            cookies = driver.get_cookies() or []
            for c in cookies:
                if c.get('name') == 'MUSIC_U' and c.get('value'):
                    music_u = c.get('value')
                if c.get('name') in ('__csrf', 'csrf_token') and c.get('value'):
                    csrf = c.get('value')
            if music_u and ('#/discover' in current_url or '#/my' in current_url or '#/home' in current_url or ('music.163.com/' in current_url)):
                logged_in = True
                break
            if music_u:
                logged_in = True
                break
            time.sleep(1)
        if not logged_in:
            print('\x1b[33m! 等待登录超时\x1b[0m')
            return None
        s = pyncm.GetCurrentSession()
        try:
            ua = driver.execute_script('return navigator.userAgent')
        except Exception:
            ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari'
        s.headers.update({'User-Agent': ua, 'Referer': 'https://music.163.com/', 'Origin': 'https://music.163.com'})
        for c in driver.get_cookies() or []:
            name = c.get('name')
            value = c.get('value')
            domain = c.get('domain') or 'music.163.com'
            path = c.get('path') or '/'
            if not name or value is None:
                continue
            if not any((domain.endswith(td) for td in target_domains)):
                continue
            s.cookies.set(name, value, domain=domain, path=path)
        if csrf and (not s.cookies.get('csrf_token')):
            s.cookies.set('csrf_token', csrf, domain='.music.163.com', path='/')
        return s
    finally:
        with suppress(Exception):
            driver.quit()

def open_image(image_path):
    system = platform.system()
    if system == 'Windows':
        os.startfile(image_path)
    elif system == 'Darwin':
        subprocess.call(['open', image_path])
    else:
        viewers = ['xdg-open', 'display', 'eog', 'ristretto', 'feh', 'gpicview']
        for viewer in viewers:
            try:
                subprocess.call([viewer, image_path])
                return
            except (FileNotFoundError, subprocess.SubprocessError):
                continue
        raise Exception('找不到合适的图片查看器')

def save_session_to_file(session, filename='session.json'):
    with open(filename, 'w') as f:
        session_data = pyncm.DumpSessionAsString(session)
        json.dump(session_data, f)
    print('\x1b[32m✓ \x1b[0m会话已保存。')

def parse_lrc(lrc_content):
    if not lrc_content:
        return []
    pattern = '\\[(\\d{2}):(\\d{2})\\.(\\d{2,3})\\](.*)'
    lyrics = []
    for line in lrc_content.split('\n'):
        match = re.match(pattern, line)
        if match:
            minutes, seconds, milliseconds, text = match.groups()
            time_seconds = int(minutes) * 60 + int(seconds) + int(milliseconds.ljust(3, '0')) / 1000
            lyrics.append((time_seconds, text))
    return sorted(lyrics, key=lambda x: x[0])

LYRIC_TRANSLATION_GAP = 0.01

def merge_lyrics(original_lyrics, translated_lyrics, song_duration=None):
    if not translated_lyrics:
        return original_lyrics
    trans_dict = {time: text for time, text in translated_lyrics}
    merged = []
    for i, (time, text) in enumerate(original_lyrics):
        merged.append((time, text))
        if time in trans_dict and trans_dict[time].strip():
            trans_time = time + LYRIC_TRANSLATION_GAP
            if i + 1 < len(original_lyrics):
                next_time = original_lyrics[i + 1][0]
                latest_before_next = next_time - LYRIC_TRANSLATION_GAP
                if latest_before_next >= trans_time:
                    trans_time = latest_before_next
                else:
                    trans_time = max(time, latest_before_next)
            else:
                tail_time = (song_duration + 0.5) if song_duration else (time + 0.5)
                trans_time = max(trans_time, tail_time, time + LYRIC_TRANSLATION_GAP)
            merged.append((trans_time, trans_dict[time]))
    return sorted(merged, key=lambda x: x[0])

def format_lrc_line(time_seconds, text):
    minutes = int(time_seconds // 60)
    seconds = int(time_seconds % 60)
    milliseconds = int(time_seconds % 1 * 100)
    return f'[{minutes:02d}:{seconds:02d}.{milliseconds:02d}]{text}'

def save_lyrics_as_lrc(lyrics, file_path):
    with open(file_path, 'w', encoding='utf-8') as f:
        for time, text in lyrics:
            f.write(format_lrc_line(time, text) + '\n')
    return file_path

@retry_with_timeout(timeout=30, retry_times=2, operation_name='获取歌词')
def get_track_lyrics(track_id):
    return track.GetTrackLyrics(track_id)

@retry_with_timeout(timeout=30, retry_times=2, operation_name='获取曲目详情')
def get_track_detail(track_ids):
    return track.GetTrackDetail(track_ids)

@retry_with_timeout(timeout=30, retry_times=2, operation_name='获取歌曲下载链接')
def get_track_audio(song_ids, level, encode_type):
    return track.GetTrackAudioV1(song_ids=song_ids, level=level, encodeType=encode_type)

@retry_with_timeout(timeout=30, retry_times=2, operation_name='获取播放列表')
def get_playlist_all_tracks(playlist_id):
    return playlist.GetPlaylistAllTracks(playlist_id)

def process_lyrics(track_id, track_name, artist_name, output_option, download_path, audio_file_path=None):
    try:
        lyric_data, error = get_track_lyrics(track_id)
        if error or not lyric_data or lyric_data.get('code') != 200 or ('lrc' not in lyric_data):
            print(f'\x1b[33m! 无法获取歌词: {track_name}\x1b[0m\x1b[K')
            return (False, None)
        track_detail, error = get_track_detail([track_id])
        song_duration = None
        if not error and track_detail and ('songs' in track_detail) and track_detail['songs']:
            song_duration = track_detail['songs'][0].get('dt', 0) / 1000
        original_lyrics = parse_lrc(lyric_data['lrc']['lyric'])
        translated_lyrics = []
        if 'tlyric' in lyric_data and lyric_data['tlyric']['lyric']:
            translated_lyrics = parse_lrc(lyric_data['tlyric']['lyric'])
        merged_lyrics = merge_lyrics(original_lyrics, translated_lyrics, song_duration)
        if not merged_lyrics:
            print(f'\x1b[33m! 未找到有效歌词: {track_name}\x1b[0m\x1b[K')
            return (False, None)
        if output_option == 'lrc' or (output_option == 'both' and download_path):
            safe_artist_name = re.sub('[\\\\/*?:"<>|]', '-', artist_name)
            safe_track_name = re.sub('[\\\\/*?:"<>|]', '-', track_name)
            lrc_path = os.path.join(download_path, f'{safe_track_name} - {safe_artist_name}.lrc')
            save_lyrics_as_lrc(merged_lyrics, lrc_path)
            print(f'\x1b[32m✓ \x1b[0m歌词已保存到 {lrc_path}\x1b[K')
        if (output_option == 'metadata' or output_option == 'both') and audio_file_path:
            lrc_content = '\n'.join([format_lrc_line(time, text) for time, text in merged_lyrics])
            return (True, lrc_content)
        return (True, None)
    except Exception as e:
        print(f'\x1b[33m! 处理歌词时出错: {e}\x1b[0m\x1b[K')
        write_to_failed_list(track_id, track_name, artist_name, f'处理歌词失败: {e}', download_path)
        return (False, None)

def add_metadata_to_audio(file_path, track_info, lyrics_content=None):
    if not MUTAGEN_INSTALLED:
        print('\x1b[33m! 未安装mutagen库，跳过添加元数据\x1b[0m\x1b[K')
        return
    try:
        file_ext = os.path.splitext(file_path)[1].lower()
        album_pic_url = track_info.get('al', {}).get('picUrl')
        album_pic_data = None
        if album_pic_url:
            response = requests.get(album_pic_url)
            if response.status_code == 200:
                album_pic_data = response.content
        title = track_info.get('name', '')
        artist = ', '.join((artist['name'] for artist in track_info.get('ar', [])))
        album = track_info.get('al', {}).get('name', '')
        track_number = str(track_info.get('no', '0'))
        release_time = track_info.get('publishTime', 0)
        if release_time > 0:
            release_year = time.strftime('%Y', time.localtime(release_time / 1000))
        else:
            release_year = ''
        if file_ext == '.mp3':
            try:
                audio = ID3(file_path)
            except:
                audio = ID3()
            audio['TIT2'] = TIT2(encoding=3, text=title)
            audio['TPE1'] = TPE1(encoding=3, text=artist)
            audio['TALB'] = TALB(encoding=3, text=album)
            audio['TRCK'] = TRCK(encoding=3, text=track_number)
            if release_year:
                audio['TDRC'] = TDRC(encoding=3, text=release_year)
            if album_pic_data:
                audio['APIC'] = APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=album_pic_data)
            if lyrics_content:
                from mutagen.id3 import USLT # pyright: ignore[reportMissingImports]
                audio['USLT'] = USLT(encoding=3, lang='eng', desc='', text=lyrics_content)
            audio.save(file_path)
        elif file_ext == '.flac':
            audio = FLAC(file_path)
            audio['TITLE'] = title
            audio['ARTIST'] = artist
            audio['ALBUM'] = album
            audio['TRACKNUMBER'] = track_number
            if release_year:
                audio['DATE'] = release_year
            if lyrics_content:
                audio['LYRICS'] = lyrics_content
            if album_pic_data:
                image = Picture()
                image.type = 3
                image.mime = 'image/jpeg'
                image.desc = 'Cover'
                image.data = album_pic_data
                img = Image.open(BytesIO(album_pic_data))
                image.width, image.height = img.size
                image.depth = 24
                audio.add_picture(image)
            audio.save()
        print(f'\x1b[32m✓ \x1b[0m已为 {os.path.basename(file_path)} 添加元数据\x1b[K')
    except Exception as e:
        print(f'\x1b[33m! 添加元数据时出错: {e}\x1b[0m\x1b[K')

def normalize_path(path):
    if path:
        path = path.strip()
        if path.startswith("'") and path.endswith("'") or (path.startswith('"') and path.endswith('"')):
            path = path[1:-1]
        path = path.rstrip()
    expanded_path = os.path.expanduser(path)
    normalized_path = os.path.normpath(expanded_path)
    if not os.path.exists(normalized_path):
        try:
            os.makedirs(normalized_path)
            print(f'\x1b[32m✓ \x1b[0m创建目录: {normalized_path}')
        except Exception as e:
            print(f'\x1b[31m× 创建目录失败: {e}\x1b[0m')
            default_path = os.path.join(os.getcwd(), 'downloads')
            os.makedirs(default_path, exist_ok=True)
            print(f'\x1b[33m! 将使用默认下载路径: {default_path}\x1b[0m')
            return default_path
    return normalized_path

def get_playlist_tracks_and_save_info(playlist_id, level, download_path):
    try:
        tracks, error = get_playlist_all_tracks(playlist_id)
        if error:
            print(f'\x1b[31m× 获取歌单列表时出错: {error}\x1b[0m\x1b[K')
            return
        if not tracks or 'songs' not in tracks:
            print('\x1b[31m× 获取歌单列表返回无效数据\x1b[0m\x1b[K')
            return
        if not os.path.exists(download_path):
            os.makedirs(download_path)
        playlist_info_filename = os.path.join(download_path, f'!#_playlist_{playlist_id}_info.txt')
        with open(playlist_info_filename, 'w', encoding='utf-8') as f:
            for track_info in tracks['songs']:
                track_id = track_info['id']
                track_name = track_info['name']
                artist_name = ', '.join((artist['name'] for artist in track_info['ar']))
                f.write(f'{track_id} - {track_name} - {artist_name}\n')
        print(f'\x1b[32m✓ \x1b[0m歌单信息已保存到 {playlist_info_filename}')
        total_tracks = len(tracks['songs'])
        for index, track_info in enumerate(tracks['songs'], start=1):
            track_id = track_info['id']
            track_name = track_info['name']
            artist_name = ', '.join((artist['name'] for artist in track_info['ar']))
            download_and_save_track(track_id, track_name, artist_name, level, download_path, track_info, index, total_tracks)
        print('=' * terminal_width + '\x1b[K')
        print(f'\x1b[32m✓ 操作已完成，歌曲已下载并保存到 \x1b[36m{download_path}\x1b[32m 文件夹中。\x1b[0m\x1b[K')
    except Exception as e:
        print(f'\x1b[31m× 获取歌单列表或下载歌曲时出错: {e}\x1b[0m\x1b[K')

def get_track_info(track_id, level, download_path):
    try:
        track_info_rsp, error = get_track_detail([track_id])
        if error:
            print(f'\x1b[31m× 获取歌曲信息时出错: {error}\x1b[0m\x1b[K')
            return
        if not track_info_rsp or 'songs' not in track_info_rsp or (not track_info_rsp['songs']):
            print(f'\x1b[31m× 获取歌曲信息返回无效数据\x1b[0m\x1b[K')
            return
        track_info = track_info_rsp['songs'][0]
        track_id = track_info['id']
        track_name = track_info['name']
        artist_name = ', '.join((artist['name'] for artist in track_info.get('ar', [])))
        download_and_save_track(track_id, track_name, artist_name, level, download_path, track_info, 1, 1)
        print(f'\x1b[32m✓ \x1b[0m歌曲 {track_name} 已保存到 {download_path} 文件夹中。\x1b[K')
    except Exception as e:
        print(f'\x1b[31m! 获取歌曲信息时出错: {e}\x1b[0m\x1b[K')

def download_and_save_track(track_id, track_name, artist_name, level, download_path, track_info=None, index=None, total=None):

    def make_safe_filename(filename):
        return re.sub('[\\\\/*?:"<>|]', '-', filename)
    try:
        url_info, error = get_track_audio([track_id], level, 'flac')
        if error:
            write_to_failed_list(track_id, track_name, artist_name, f'获取下载链接失败: {error}', download_path)
            print(f'\x1b[31m! 获取曲目 {track_name} 的下载链接时出错: {error}\x1b[0m\x1b[K')
            return
        if not url_info or 'data' not in url_info or (not url_info['data']):
            write_to_failed_list(track_id, track_name, artist_name, '获取下载链接返回无效数据', download_path)
            print(f'\x1b[31m! 获取曲目 {track_name} 的下载链接返回无效数据\x1b[0m\x1b[K')
            return
        url = url_info['data'][0].get('url')
        if url:
            max_retries = 2
            retry_count = 0
            while retry_count <= max_retries:
                try:
                    response = requests.get(url, stream=True, timeout=30)
                    if response.status_code != 200:
                        print(f'\x1b[31m× 获取 URL 时出错: {response.status_code} - {response.text}\x1b[0m\x1b[K')
                        write_to_failed_list(track_id, track_name, artist_name, f'HTTP错误: {response.status_code}', download_path)
                        return
                    content_disposition = response.headers.get('content-disposition')
                    if content_disposition:
                        filename = content_disposition.split('filename=')[-1].strip('"')
                    else:
                        filename = f'{track_id}.flac'
                    os.makedirs(download_path, exist_ok=True)
                    safe_filename = make_safe_filename(f'{track_name} - {artist_name}{os.path.splitext(filename)[1]}')
                    safe_filepath = os.path.join(download_path, safe_filename)
                    file_size = int(response.headers.get('content-length', 0))
                    progress_status = ''
                    # ===== 新进度条逻辑（单行反色，宽终端才启用） =====
                    try:
                        term_w = terminal_width  # 全局在主入口已定义
                    except NameError:
                        term_w, _ = get_terminal_size()
                    digits = len(str(total)) if (index is not None and total is not None) else 0
                    idx_str = f"[{index:0{digits}d}/{total}] " if (index is not None and total is not None) else ''
                    # 预估基础行（用于是否采用新样式判断）
                    base_core = f"100.0% {idx_str}正在下载:...   99.99MB/99.99MB 99999KB/s 9999s"
                    use_single_line = term_w >= 60 and len(base_core) <= term_w - 2  # 预留一点余量
                    downloaded = 0
                    last_downloaded = 0
                    last_update_time = time.time()
                    start_time = time.time()
                    speed = 0.0
                    used_single_line_style = False
                    fallback_header_printed = False  # 窄终端备用模式是否已输出首行

                    def human_eta(rem_bytes, spd_bytes):
                        if spd_bytes <= 0 or rem_bytes <= 0:
                            return '--'
                        eta = rem_bytes / spd_bytes
                        if eta < 60:
                            return f'{int(eta)}s'
                        elif eta < 3600:
                            m = int(eta // 60)
                            s = int(eta % 60)
                            return f'{m}m{s:02d}s'
                        else:
                            h = int(eta // 3600)
                            m = int((eta % 3600) // 60)
                            return f'{h}h{m:02d}m'

                    # 宽度计算工具：考虑中日韩全角字符宽度=2，并修正省略号“…”等特殊字符

                    def cell_width(ch: str) -> int:
                        if not ch:
                            return 0
                        # 常见零宽字符（组合符号/格式控制）按0宽处理
                        cat = unicodedata.category(ch)
                        if cat in ('Mn', 'Me', 'Cf'):
                            return 0
                        # 单字符省略号在部分终端为宽字符，按2宽处理以避免对齐错位
                        if ch == '…':
                            return 2
                        eaw = unicodedata.east_asian_width(ch)
                        if eaw in ('W', 'F'):
                            return 2
                        if eaw == 'A' and cat.startswith('S'):
                            return 2
                        return 1

                    def display_width(text: str) -> int:
                        return sum(cell_width(c) for c in text)

                    def truncate_filename(fname: str, max_disp: int) -> str:
                        # 保留扩展名
                        name_no_ext, ext = os.path.splitext(fname)
                        ext_w = display_width(ext)
                        ell_w = display_width('…')
                        # 如果本身就适合
                        if display_width(fname) <= max_disp:
                            return fname
                        # 预留扩展名与省略号
                        remain = max_disp - ext_w - ell_w
                        if remain <= 1:
                            # 极端情况下直接截掉
                            return '…' + ext
                        # 截取
                        acc = ''
                        w = 0
                        for ch in name_no_ext:
                            cw = cell_width(ch)
                            if w + cw > remain:
                                break
                            acc += ch
                            w += cw
                        return acc + '…' + ext

                    with open(safe_filepath, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=64 * 1024):
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded += len(chunk)
                            now = time.time()
                            # 超时 / 停滞检测（10 秒无进展）
                            if now - last_update_time >= 10:
                                if downloaded == last_downloaded:
                                    print(f'\n\x1b[33m! 下载 {safe_filename} 停滞，正在重试...\x1b[0m\x1b[K')
                                    break
                                last_downloaded = downloaded
                                last_update_time = now
                            # 进度显示
                            if file_size > 0:
                                percent = downloaded / file_size
                            else:
                                percent = 0.0
                            elapsed = now - start_time
                            if elapsed > 0:
                                speed = downloaded / elapsed  # bytes/s
                            spd_kb = speed / 1024
                            if file_size > 0:
                                remaining = file_size - downloaded
                            else:
                                remaining = -1
                            eta_str = human_eta(remaining, speed) if remaining > 0 else '--'
                            downloaded_mb = downloaded / 1024 / 1024
                            total_mb = file_size / 1024 / 1024 if file_size > 0 else 0
                            if use_single_line:
                                used_single_line_style = True
                                # 每次渲染重新测量终端宽度
                                try:
                                    term_w, _ = get_terminal_size()
                                except Exception:
                                    pass
                                # 重新判断是否仍适合单行
                                dynamic_base = f"{idx_str}正在下载:... 100.0%  99.99MB/99.99MB 99999KB/s 9999s"
                                if not (term_w >= 60 and display_width(dynamic_base) <= term_w - 2):
                                    # 切换到窄终端备用模式，确保稍后打印首行
                                    use_single_line = False
                                    # 立即打印首行（若尚未打印）
                                    if not fallback_header_printed:
                                        # 在窄终端打印精简标题行，必要时对文件名进行截断
                                        progress_status = idx_str
                                        try:
                                            term_w, _ = get_terminal_size()
                                        except Exception:
                                            pass
                                        prefix_plain = f"{progress_status}正在下载: "
                                        max_name_w = max(0, term_w - display_width(prefix_plain) - 1)
                                        disp_name = truncate_filename(safe_filename, max_name_w) if display_width(safe_filename) > max_name_w else safe_filename
                                        print(f'\x1b[94m{progress_status}正在下载: {disp_name}\x1b[0m')
                                        fallback_header_printed = True
                                    continue
                                # 百分比文本（不带前导0）
                                if file_size > 0:
                                    pct_val = percent * 100
                                    percent_raw = f"{pct_val:.1f}%"
                                    if pct_val < 10:
                                        percent_raw = percent_raw.lstrip('0')  # 5.3%
                                else:
                                    percent_raw = '---%'
                                percent_field_width = 6  # 容纳 100.0% (6字符)
                                if len(percent_raw) < percent_field_width:
                                    pad_total = percent_field_width - len(percent_raw)
                                    left_pad = pad_total // 2
                                    right_pad = pad_total - left_pad
                                    percent_txt = ' ' * left_pad + percent_raw + ' ' * right_pad
                                else:
                                    percent_txt = percent_raw[:percent_field_width]
                                size_txt = f"{downloaded_mb:.2f}MB/{total_mb:.2f}MB" if file_size > 0 else f"{downloaded_mb:.2f}MB/??MB"
                                # 无千分位分隔的速度
                                spd_txt = (f"{spd_kb:.0f}KB/s" if spd_kb >= 100 else f"{spd_kb:.1f}KB/s") if spd_kb > 0 else '0KB/s'
                                right_part = f"{size_txt} {spd_txt} {eta_str}".strip()
                                base_left_prefix = f"{idx_str}正在下载:"
                                percent_part = f" {percent_txt}"  # 前置空格分隔
                                right_w = display_width(right_part)
                                static_left_w = display_width(base_left_prefix) + display_width(percent_part)
                                max_name_w = term_w - right_w - static_left_w - 1
                                disp_name = safe_filename
                                if max_name_w <= 5:
                                    use_single_line = False
                                    continue
                                if display_width(disp_name) > max_name_w:
                                    disp_name = truncate_filename(disp_name, max_name_w)
                                left_part = f"{base_left_prefix}{disp_name}{percent_part}"
                                left_w = display_width(left_part)
                                total_w = left_w + 1 + right_w
                                if total_w > term_w:
                                    over = total_w - term_w
                                    adjust_max = max_name_w - over
                                    if adjust_max > 3:
                                        disp_name = truncate_filename(disp_name, adjust_max)
                                        left_part = f"{base_left_prefix}{disp_name}{percent_part}"
                                        left_w = display_width(left_part)
                                        total_w = left_w + 1 + right_w
                                spaces_w = term_w - (left_w + right_w)
                                if spaces_w < 1:
                                    spaces_w = 1
                                line_full = left_part + ' ' * spaces_w + right_part
                                # 反色填充
                                fill_cells = int(term_w * percent)
                                if fill_cells < 0:
                                    fill_cells = 0
                                if fill_cells > term_w:
                                    fill_cells = term_w
                                acc = ''
                                acc_w = 0
                                i = 0
                                while i < len(line_full) and acc_w < fill_cells:
                                    ch = line_full[i]
                                    acc += ch
                                    acc_w += cell_width(ch)
                                    i += 1
                                remainder = line_full[i:]
                                sys.stdout.write('\r' + (f'\x1b[7;33m{acc}\x1b[0m\x1b[33m' + remainder + '\x1b[0m'))
                                cur_disp_w = display_width(line_full)
                                if cur_disp_w < term_w:
                                    sys.stdout.write(' ' * (term_w - cur_disp_w))
                                sys.stdout.flush()
                            else:
                                # 旧窄终端备用方案：只打印一次标题行
                                if not fallback_header_printed:
                                    progress_status = idx_str
                                    try:
                                        term_w, _ = get_terminal_size()
                                    except Exception:
                                        pass
                                    prefix_plain = f"{progress_status}正在下载: "
                                    max_name_w = max(0, term_w - display_width(prefix_plain) - 1)
                                    disp_name = truncate_filename(safe_filename, max_name_w) if display_width(safe_filename) > max_name_w else safe_filename
                                    print(f'\x1b[94m{progress_status}正在下载: {disp_name}\x1b[0m')
                                    fallback_header_printed = True
                                # 不再实时输出进度，完成后输出成功信息
                        else:
                            # for-else：正常完成循环（未 break）
                            pass
                    if downloaded < file_size and file_size > 0:
                        retry_count += 1
                        if retry_count <= max_retries:
                            print(f'\x1b[33m! 下载不完整，正在重试 ({retry_count}/{max_retries})...\x1b[0m\x1b[K')
                            continue
                        else:
                            write_to_failed_list(track_id, track_name, artist_name, '下载不完整', download_path)
                            print(f'\x1b[31m× 多次尝试下载失败: {safe_filename}\x1b[0m\x1b[K')
                            return
                    break
                except (Timeout, ConnectionError, RequestException) as e:
                    retry_count += 1
                    if retry_count <= max_retries:
                        print(f'\x1b[33m! 下载超时，正在重试 ({retry_count}/{max_retries})...\x1b[0m\x1b[K')
                    else:
                        write_to_failed_list(track_id, track_name, artist_name, f'下载失败: {e}', download_path)
                        print(f'\x1b[31m× 多次尝试下载失败: {e}\x1b[0m\x1b[K')
                        return
            if 'used_single_line_style' in locals() and used_single_line_style:
                # 清除当前反色行
                try:
                    sys.stdout.write('\r' + ' ' * term_w + '\r')
                except Exception:
                    pass
                print(f'\x1b[32m✓ 已下载{progress_status}\x1b[0m{safe_filename}\x1b[K')
                # try:
                #     term_w, _ = get_terminal_size()
                # except Exception:
                #     pass
                # prefix_plain = '✓ 已下载: '
                # max_name_w = max(0, term_w - display_width(prefix_plain) - 1)
                # disp_name = safe_filename if display_width(safe_filename) <= max_name_w else truncate_filename(safe_filename, max_name_w)
                # print(f'\x1b[32m✓ 已下载: \x1b[0m{disp_name}\x1b[K')
            else:
                # 旧样式成功信息
                try:
                    # 清除当前行并上移一行后清除上一行
                    sys.stdout.write('\r\x1b[K\x1b[1A\x1b[K')
                    sys.stdout.flush()
                except Exception:
                    pass
                progress_status = f'[{index}/{total}] ' if (index is not None and total is not None) else ''
                try:
                    term_w, _ = get_terminal_size()
                except Exception:
                    pass
                prefix_plain = f"✓ 已下载{progress_status}"
                max_name_w = max(0, term_w - display_width(prefix_plain) - 1)
                disp_name = safe_filename if display_width(safe_filename) <= max_name_w else truncate_filename(safe_filename, max_name_w)
                print(f'\x1b[32m✓ 已下载{progress_status}\x1b[0m{disp_name}\x1b[K')
            try:
                audio = MutagenFile(safe_filepath)
                if audio is not None and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                    duration = audio.info.length
                    if duration < 35:
                        print(f'\x1b[33m! 警告: {safe_filename} 音频长度仅为 {duration:.1f} 秒，可能为试听片段。\x1b[0m\x1b[K')
                        print('\x1b[33m  出现这种问题可能是您没有VIP权限或网易云变更接口所致。\x1b[0m\x1b[K')
                        write_to_failed_list(track_id, track_name, artist_name, f'音频长度过短({duration:.1f}s)，可能为试听片段', download_path)
            except Exception as e:
                print(f'\x1b[33m! 检查音频长度时出错: {e}\x1b[0m\x1b[K')
            if not track_info and url_info['data'][0].get('id'):
                try:
                    track_detail, error = get_track_detail([url_info['data'][0]['id']])
                    if not error and track_detail and ('songs' in track_detail) and track_detail['songs']:
                        track_info = track_detail['songs'][0]
                    elif error:
                        print(f'\x1b[33m! 获取曲目详情失败: {error}\x1b[0m\x1b[K')
                except Exception as e:
                    print(f'\x1b[33m! 获取曲目详情失败: {e}\x1b[0m\x1b[K')
            lyrics_success, lyrics_content = process_lyrics(track_id, track_name, artist_name, lyrics_option, download_path, safe_filepath) # type: ignore # globaled
            if track_info:
                add_metadata_to_audio(safe_filepath, track_info, lyrics_content if lyrics_success else None)
            else:
                write_to_failed_list(track_id, track_name, artist_name, '无法添加元数据: 缺少曲目信息', download_path)
                print('\x1b[33m! 无法添加元数据: 缺少曲目信息\x1b[0m\x1b[K')
        else:
            if terminal_width >= 88:
                sys.stdout.write('\r\x1b[1A\x1b[K')
            write_to_failed_list(track_id, track_name, artist_name, '无可用下载链接（可能凭据错误或歌曲已下架）', download_path)
            print(f'\x1b[31m! 无法下载 {track_name} - {artist_name}, 详情请查看 !#_FAILED_LIST.txt\x1b[0m\x1b[K')
    except (KeyError, IndexError) as e:
        if terminal_width >= 88:
            sys.stdout.write('\r\x1b[1A\x1b[K')
        write_to_failed_list(track_id, track_name, artist_name, f'URL信息错误: {e}', download_path)
        print(f'\x1b[31m! 访问曲目 {track_name} - {artist_name} 的URL信息时出错: {e}\x1b[0m\x1b[K')
    except Exception as e:
        if terminal_width >= 88:
            sys.stdout.write('\r\x1b[1A\x1b[K')
        write_to_failed_list(track_id, track_name, artist_name, f'未知下载错误: {e}', download_path)
        print(f'\x1b[31m! 下载歌曲时出错: {e}\x1b[0m\x1b[K')

def write_to_failed_list(track_id, track_name, artist_name, reason, download_path):
    failed_list_path = os.path.join(download_path, '!#_FAILED_LIST.txt')
    if not os.path.exists(failed_list_path):
        with open(failed_list_path, 'w', encoding='utf-8') as f:
            f.write('此处列举了下载失败的歌曲\n可能的原因：\n1.歌曲为单曲付费曲目 \n2.歌曲已下架 \n3.地区限制（如VPN） \n4.网络问题 \n5.VIP曲目但账号无VIP权限\n=== === === === === === === === === === === ===\n\n')
    with open(failed_list_path, 'a', encoding='utf-8') as f:
        f.write(f'ID: {track_id} - 歌曲: {track_name} - 艺术家: {artist_name} - 原因: {reason}\n')

def load_session_from_file(filename='session.json'):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            session_data = json.load(f)
        session = pyncm.LoadSessionFromString(session_data)
        pyncm.SetCurrentSession(session)
        print('\x1b[32m✓ \x1b[0m会话已从文件加载。')
        if DEBUG:
            print('当前 Cookie 信息：')
            for cookie in session.cookies:
                print(f'  {cookie.name}: {cookie.value} (Domain: {cookie.domain})')
            print(session)
            input('按回车键继续...')
        return session
    else:
        return None

def get_current_nickname(default_name: str='未登录用户') -> str:
    """获取当前登录用户昵称，失败则返回默认值。"""
    try:
        status = login.GetCurrentLoginStatus()
        if DEBUG:
            print('当前登录状态：', status)
            input('按回车键继续...')
        if isinstance(status, dict):
            prof = status.get('profile') or {}
            name = prof.get('nickname') or prof.get('nickName')
            if name:
                return str(name)
        return default_name
    except Exception:
        return default_name

def _parse_user_info_from_status(status: dict) -> dict:
    """从 login.GetCurrentLoginStatus() 的返回结构中提取昵称、用户ID和VIP信息，尽可能兼容多种字段名。"""
    nickname = None
    user_id = None
    vip = None
    if not isinstance(status, dict):
        return {'nickname': nickname, 'user_id': user_id, 'vip': vip}
    prof = status.get('profile') or {}
    nickname = prof.get('nickname') or prof.get('nickName') or status.get('nickname')
    user_id = prof.get('userId') or status.get('userId') or status.get('account', {}).get('id') if isinstance(status.get('account'), dict) else status.get('userId')
    vip = prof.get('vipType') or status.get('vipType')
    if vip is None:
        vip_block = prof.get('vip') if isinstance(prof.get('vip'), dict) else None
        if isinstance(vip_block, dict):
            vip = vip_block.get('type') or vip_block.get('vipType')
    return {'nickname': nickname, 'user_id': user_id, 'vip': vip}

def display_user_info(session=None, silent=False):
    """打印当前会话的用户名与 VIP 状态（尽量容错）。

    如果传入 session，会先将其设为当前 pyncm 会话以便 login.GetCurrentLoginStatus() 使用。
    """
    try:
        if session is not None:
            with suppress(Exception):
                pyncm.SetCurrentSession(session)
        if USER_INFO_CACHE['user_id'] is not None:
            if DEBUG:
                print('skipped')
            nick = USER_INFO_CACHE.get('nickname') or '未知用户'
            uid = USER_INFO_CACHE.get('user_id') or '-'
            vip_val = USER_INFO_CACHE.get('vip')
            vip_str = '未知'
            if not silent:
                print(f'\x1b[32m✓ 登录用户: \x1b[36m{nick}\x1b[0m (ID: {uid}) VIP: \x1b[33m{vip_str}\x1b[0m' if uid != '-' else f'\x1b[31m× 登录失败！\n  删除session.json后重新登录或反馈给开发者。\x1b[0m')
            return USER_INFO_CACHE
        status = login.GetCurrentLoginStatus()
        info = _parse_user_info_from_status(status if isinstance(status, dict) else {})
        nick = info.get('nickname') or '未知用户'
        uid = info.get('user_id') or '-'
        vip_val = info.get('vip')
        vip_str = '未知'
        try:
            if vip_val is None:
                vip_str = '非VIP'
            else:
                vip_int = int(vip_val)
                vip_str = 'VIP' if vip_int > 0 else '非VIP'
        except Exception:
            vip_str = str(vip_val)
        if not silent:
            send_notification('登录成功', f'欢迎，{nick}！')
            print(f'\x1b[32m✓ 已登录: \x1b[36m{nick}\x1b[0m (ID: {uid}) 状态: \x1b[33m{vip_str}\x1b[0m' if uid != '-' else f'\x1b[31m× 登录失败！\n  删除session.json后重新登录或反馈给开发者。\x1b[0m')
        USER_INFO_CACHE.update(info)
        return info
    except Exception as e:
        with suppress(Exception):
            print(f'\x1b[33m! 无法获取用户信息: {e}\x1b[0m')
        return {'nickname': None, 'user_id': None, 'vip': None}
    
if __name__ == '__main__':
    if 'DEBUG' not in globals() or not isinstance(DEBUG, bool):
        DEBUG = False
    try:
        terminal_width, _ = get_terminal_size()
        if terminal_width >= 88:
            print(" __. __. ____. . . . . . . .  ____. . ___. . \x1b[0m.\x1b[0m\x1b[0m \x1b[0m\x1b[0m.\x1b[0m\x1b[0m \x1b[0m\x1b[0m.\x1b[0m . . . . .  ___. . . . . . .  __. . . \n/\\ \\/\\ \\/\\. _`\\.  /'\\_/`\\. . /\\. _`\\ /\\_ \\.\x1b[0m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[0m \x1b[0m. . . .  /\\_ \\.  __. . . . /\\ \\__.  \n\\ \\ `\\\\ \\ \\ \\/\\_\\/\\. . . \\.  \\ \\ \\L\x1b[0m\\\x1b[0m\x1b[0m \x1b[0m\x1b[31m\\\x1b[0m\x1b[31m/\x1b[0m\x1b[31m/\x1b[0m\x1b[31m\\\x1b[0m \x1b[0m\\\x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[0m.\x1b[0m\x1b[0m \x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m.\x1b[0m . __. __\\//\\ \\ /\\_\\. . ___\\ \\ ,_\\. \n \\ \\ , ` \\ \\ \\/_/\\ \\ \\__\\ \\.  \\ \\\x1b[0m \x1b[0m\x1b[31m,\x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m/\x1b[0m\x1b[31m \x1b[0m\x1b[31m\\\x1b[0m\x1b[0m \x1b[0m\\ \x1b[31m\\\x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[0m \x1b[0m/'__`\\ /\\ \\/\\ \\ \\ \\ \\\\/\\ \\. /',__\\ \\ \\/. \n. \\ \\ \\`\\ \\ \\ \\L\\ \\ \\ \\_/\\ \\.  \\\x1b[0m \x1b[0m\x1b[31m\\\x1b[0m\x1b[31m \x1b[0m\x1b[31m\\\x1b[0m\x1b[31m/\x1b[0m\x1b[0m.\x1b[0m  \\\x1b[0m_\x1b[0m\x1b[0m\\\x1b[0m\x1b[31m \x1b[0m\x1b[31m\\\x1b[0m\x1b[31m_\x1b[0m\x1b[31m/\x1b[0m\x1b[31m\\\x1b[0m\x1b[31m \x1b[0m\x1b[0m\\\x1b[0m\x1b[0mL\x1b[0m\\.\\\\ \\ \\_\\ \\ \\_\\ \\\\ \\ \\/\\__, `\\ \\ \\_ \n.  \\ \\_\\ \\_\\ \\____/\\ \\_\\\\ \\_\\. \x1b[31m \x1b[0m\x1b[31m\\\x1b[0m\x1b[31m \x1b[0m\x1b[31m\\\x1b[0m\x1b[0m_\x1b[0m\\. \x1b[0m \x1b[0m\x1b[31m/\x1b[0m\x1b[31m\\\x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m\\\x1b[0m\x1b[31m \x1b[0m\x1b[31m\\\x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m/\x1b[0m\x1b[0m.\x1b[0m\\_\\/`____ \\/\\____\\ \\_\\/\\____/\\ \\__\\\n. . \\/_/\\/_/\\/___/. \\/_/ \\/_/.\x1b[0m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m\\\x1b[0m/_/.\x1b[31m \x1b[0m\x1b[31m \x1b[0m\x1b[31m\\\x1b[0m\x1b[31m/\x1b[0m\x1b[31m_\x1b[0m\x1b[0m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m/\x1b[0m\x1b[31m\\\x1b[0m\x1b[0m/\x1b[0m\x1b[0m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m/\x1b[0m\x1b[31m\\\x1b[0m\x1b[31m/\x1b[0m\x1b[0m_\x1b[0m/`/___/> \\/____/\\/_/\\/___/. \\/__/\n. . . . . . . . . . . . . . . \x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[0m \x1b[0m. .\x1b[0m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[0m \x1b[0m. \x1b[0m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[0m.\x1b[0m .\x1b[0m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[0m \x1b[0m.  /\\___/. . . . . . . . . . .  \n. . . . . . . . . . . . . . .\x1b[0m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[0m \x1b[0m. .\x1b[0m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[0m \x1b[0m. .\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m . \x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m.  \\/__/. . . . . . . . . . . . \n ____. . . . . . . . . . . . .\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[0m.\x1b[0m ___\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[0m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[0m.\x1b[0m . \x1b[0m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m. .  __. . . . . . . . . . . .  \n/\\. _`\\. . . . . . . . . . . .\x1b[0m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m \x1b[0m\x1b[0m/\x1b[0m\\_ \\\x1b[0m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[0m.\x1b[0m . .\x1b[31m \x1b[0m\x1b[31m.\x1b[0m\x1b[31m \x1b[0m\x1b[31m.\x1b[0m .  /\\ \\. . . . . . . . . . . . \n\\ \\ \\/\\ \\.  ___.  __. __. __.  \x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m\\\x1b[0m\x1b[0m/\x1b[0m/\\ \\.\x1b[0m \x1b[0m\x1b[0m.\x1b[0m\x1b[0m \x1b[0m\x1b[0m \x1b[0m___. .\x1b[35m \x1b[0m\x1b[31m \x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[0m.\x1b[0m .  \\_\\ \\. .  __. _ __. . . . . \n \\ \\ \\ \\ \\ / __`\\/\\ \\/\\ \\/\\ \\/' \x1b[0m_\x1b[0m\x1b[31m \x1b[0m\x1b[31m`\x1b[0m\x1b[31m\\\x1b[0m\x1b[31m\\\x1b[0m\x1b[0m \x1b[0m\\ \\.  / __\x1b[0m`\x1b[0m\x1b[0m\\\x1b[0m\x1b[31m \x1b[0m\x1b[31m/\x1b[0m\x1b[31m'\x1b[0m\x1b[31m_\x1b[0m\x1b[0m_\x1b[0m`\\.  /'_` \\. /'__`/\\`'__\\. . . . \n. \\ \\ \\_\\ /\\ \\L\\ \\ \\ \\_/ \\_/ /\\ \\\x1b[0m/\x1b[0m\x1b[31m\\\x1b[0m\x1b[31m \x1b[0m\x1b[31m\\\x1b[0m\x1b[31m\\\x1b[0m\x1b[31m_\x1b[0m\x1b[31m\\\x1b[0m\x1b[31m \x1b[0m\x1b[0m\\\x1b[0m\x1b[0m_\x1b[0m\x1b[0m/\x1b[0m\x1b[0m\\\x1b[0m\x1b[0m \x1b[0m\x1b[31m\\\x1b[0m\x1b[31mL\x1b[0m\x1b[31m\\\x1b[0m\x1b[31m \x1b[0m\x1b[31m/\x1b[0m\x1b[31m\\\x1b[0m\x1b[0m \x1b[0m\\L\\.\\_/\\ \\L\\ \\/\\. __\\ \\ \\/. . . .  \n.  \\ \\____\\ \\____/\\ \\___x___/\\ \\_\\ \\\x1b[0m_\x1b[0m\x1b[31m/\x1b[0m\x1b[31m\\\x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m\\\x1b[0m\x1b[31m \x1b[0m\x1b[31m\\\x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[31m_\x1b[0m\x1b[0m_\x1b[0m\x1b[0m\\\x1b[0m \\__/.\\_\\ \\___,_\\ \\____\\ \\_\\. . . .  \n. . \\/___/ \\/___/. \\/__//__/. \\/_/\\/_\\/_\x1b[0m_\x1b[0m\x1b[0m_\x1b[0m\x1b[0m_\x1b[0m\x1b[0m/\x1b[0m\x1b[0m\\\x1b[0m\x1b[0m/\x1b[0m\x1b[0m_\x1b[0m__/ \\/__/\\/_/\\/__,_ /\\/____/\\/_/. . . .  \n\n\n"+" "*49+"Netease Cloud Music Playlist Downloader")
        else:
            print('\n\nNetease Cloud Music Playlist Downloader')
            print('\x1b[33m! 您的终端窗口宽度小于88个字符，部分特性已被停用。\x1b[0m')
            print('\x1b[44;37m若要完整展示程序特性和下载进度，请调整窗口宽度或字体大小到可以完整显示这行后重新执行脚本\x1b[0m\n\n')
            '\n    ========================================================================================================\n            '
        if DEBUG:
            print('\x1b[33m! 调试模式已启用。\x1b[0m')
            print('\x1b[33m  调试模式可能会输出大量冗余或敏感信息。\x1b[0m')
            print('\x1b[33m  如果不需要调试信息，请删除或注释掉 DEBUG = True。\x1b[0m')
        session = load_session_from_file()
        if session:
            print('  使用保存的会话登录。')
            print('\x1b[33m  如需更换账号，请删除 session.json 文件后重新运行脚本。\x1b[0m')
            with suppress(Exception):
                display_user_info(session)
            time.sleep(2)
        else:
            try:
                session = get_qrcode()
                if session:
                    save_session_to_file(session)
                time.sleep(3)
            except Exception as e:
                print(e)
                input('  按回车退出程序...')
                sys.exit(1)
        default_path = os.path.join(os.getcwd(), 'downloads')
        config = {'download_path': default_path, 'mode': 'playlist', 'playlist_id': None, 'track_id': None, 'level': 'exhigh', 'lyrics_option': 'both'}
        preview_cache = {'playlist': {'id': None, 'name': None, 'count': None, 'error': None}, 'track': {'id': None, 'name': None, 'artist': None, 'error': None}}

        def color_text(text, color_code):
            return f'\x1b[{color_code}m{text}\x1b[0m'

        def set_download_path():
            print('\n\x1b[2m' + '=' * (terminal_width//2) + '\x1b[0m')
            print('> 下载路径编辑')
            print('\n  输入下载路径（可拖拽文件夹至此），按回车确认。')
            ipt = input('\x1b[36m  > \x1b[0m\x1b[4m')
            print('\x1b[0m', end='')
            if not ipt.strip():
                config['download_path'] = default_path
            else:
                config['download_path'] = normalize_path(ipt)

        def toggle_mode():
            config['mode'] = 'track' if config['mode'] == 'playlist' else 'playlist'

        def input_id_for_mode():
            print('\n\x1b[2m' + '=' * (terminal_width//2) + '\x1b[0m')
            print('> 配置 ID')
            print('\x1b[94mi 有关于歌单 ID 和单曲 ID 的说明，请参阅 https://github.com/padoru233/NCM-Playlist-Downloader/blob/main/README.md#使用方法\x1b[0m')

            def extract_id_and_type(text: str):
                if not text:
                    return (None, None)
                s = text.strip().strip('"\'')
                if re.fullmatch('\\d+', s):
                    return (s, None)
                m = re.search('[?&]id=(\\d+)', s)
                found_id = m.group(1) if m else None
                lower = s.lower()
                inferred = None
                if re.search('(?:#|/)(?:.*)playlist', lower) or '/playlist' in lower:
                    inferred = 'playlist'
                elif re.search('(?:#|/)(?:.*)song', lower) or '/song' in lower or '/track' in lower:
                    inferred = 'track'
                if found_id:
                    return (found_id, inferred)
                m2 = re.search('(\\d{5,})', s)
                if m2:
                    return (m2.group(1), inferred)
                return (None, None)
            prompt = '  请输入歌单 ID\x1b[36m > \x1b[0m' if config['mode'] == 'playlist' else '  请输入单曲 ID\x1b[36m > \x1b[0m'
            ipt = input(prompt).strip()
            final_id = None
            final_type = None
            if not ipt:
                cb = get_clipboard_text() or ''
                if cb:
                    print(f'  检测到剪贴板内容：{cb}')
                    extracted_id, extracted_type = extract_id_and_type(cb)
                    if extracted_id:
                        final_id = extracted_id
                        final_type = extracted_type
                    else:
                        print('\x1b[33m! 剪贴板内容无法解析为有效ID或链接，视为未指定。\x1b[0m')
                else:
                    print('\x1b[33m! 未输入且剪贴板为空，ID 被视为未指定。\x1b[0m')
            else:
                extracted_id, extracted_type = extract_id_and_type(ipt)
                if extracted_id:
                    final_id = extracted_id
                    final_type = extracted_type
                else:
                    print('\x1b[33m! 输入未包含有效ID或可解析链接，视为未指定。\x1b[0m')
            if final_id:
                if not final_type:
                    final_type = config['mode']
                if final_type == 'playlist':
                    if config['mode'] != 'playlist':
                        print('\x1b[33m! 检测到歌单链接/ID，但当前为单曲模式，已自动切换到歌单模式。\x1b[0m')
                        config['mode'] = 'playlist'
                    config['playlist_id'] = final_id
                    config['track_id'] = None
                else:
                    if config['mode'] != 'track':
                        print('\x1b[33m! 检测到单曲链接/ID，但当前为歌单模式，已自动切换到单曲模式。\x1b[0m')
                        config['mode'] = 'track'
                    config['track_id'] = final_id
                    config['playlist_id'] = None
            elif config['mode'] == 'playlist':
                config['playlist_id'] = None
            else:
                config['track_id'] = None
            refresh_preview()

        def choose_level():
            print('\n\x1b[2m' + '=' * (terminal_width//2) + '\x1b[0m')
            print('> 音质 选项')
            print('\x1b[94mi 有关于音质选项的详细说明，请参阅 https://github.com/padoru233/NCM-Playlist-Downloader/blob/main/README.md#音质说明\x1b[0m')
            print('可使用的音质选项：')
            opts = [('standard', '标准\t  MP3\t  128kbps'), ('exhigh', '极高\t  MP3\t  320kbps'), ('lossless', '无损\t  FLAC\t  48kHz/16bit'), ('hires', '高解析度\tFLAC\t192kHz/16bit'), ('jymaster', '高清臻音\tFLAC\t96kHz/24bit')]
            for i, (val, zh) in enumerate(opts, 1):
                flag = '\x1b[44m' if config['level'] == val else ''
                zh = zh.expandtabs(8)
                print(f'\x1b[36m[{i}]\x1b[0m {flag}{zh} ({val})\x1b[0m ')
            print('\n\x1b[36m[0]\x1b[0m 取消')
            sel = input('\x1b[36m> \x1b[0m').strip()
            mapping = {str(i): v for i, (v, _) in enumerate(opts, 1)}
            if sel in mapping:
                config['level'] = mapping[sel]

        def choose_lyrics():
            print('\x1b[2m' + '=' * (terminal_width//2) + '\x1b[0m')
            print('> 歌词 选项')
            print('保存歌词的方式：')
            opts = [
                ('both', '写入标签和文件'),
                ('metadata', '只写入标签'),
                ('lrc', '只写入lrc文件'),
                ('none', '不处理歌词'),
            ]
            for i, (val, zh) in enumerate(opts, 1):
                flag = '\x1b[44m' if config.get('lyrics_option') == val else ''
                print(f"\x1b[36m[{i}]\x1b[0m {flag}{zh} ({val})\x1b[0m ")
            print('\n\x1b[36m[0]\x1b[0m 取消')
            sel = input('\x1b[36m> \x1b[0m').strip()
            mapping = {str(i): v for i, (v, _) in enumerate(opts, 1)}
            if sel in mapping:
                config['lyrics_option'] = mapping[sel]

        def refresh_preview():
            try:
                if config['mode'] == 'track' and config['track_id']:
                    if preview_cache['track']['id'] == config['track_id']:
                        return
                    info, err = get_track_detail([config['track_id']])
                    if err or not info or (not info.get('songs')):
                        preview_cache['track'] = {'id': config['track_id'], 'name': None, 'artist': None, 'error': str(err) if err else '无结果'} # pyright: ignore[reportArgumentType]
                    else:
                        song = info['songs'][0]
                        name = song.get('name', '')
                        artist = ', '.join((a.get('name', '') for a in song.get('ar', [])))
                        preview_cache['track'] = {'id': config['track_id'], 'name': name, 'artist': artist, 'error': None} # pyright: ignore[reportArgumentType]
                elif config['mode'] == 'playlist' and config['playlist_id']:
                    if preview_cache['playlist']['id'] == config['playlist_id']:
                        return
                    lst, err = get_playlist_all_tracks(config['playlist_id'])
                    if DEBUG:
                        print(f'调试信息：\x1b[90m{lst}\x1b[0m')
                        input('按回车键继续...')
                    if err or not lst or 'songs' not in lst:
                        preview_cache['playlist'] = {'id': config['playlist_id'], 'name': None, 'count': None, 'error': str(err) if err else '无结果'} # type: ignore
                    else:
                        songs = lst.get('songs', []) or []
                        count = len(songs)
                        first_song_name = songs[0].get('name') if songs else None
                        preview_cache['playlist'] = {'id': config['playlist_id'], 'name': first_song_name, 'count': count, 'error': None} # type: ignore
            except Exception as e:
                if config['mode'] == 'track':
                    preview_cache['track'] = {'id': config.get('track_id'), 'name': None, 'artist': None, 'error': str(e)} # type: ignore # type: ignore
                else:
                    preview_cache['playlist'] = {'id': config.get('playlist_id'), 'name': None, 'count': None, 'error': str(e)} # type: ignore

        def render_menu(display_only=False):
            print('\x1b[1J\x1b[H\x1b[0J', end='')
            if DEBUG:
                print(display_user_info(silent=True))
            display_user_info(silent=True)
            user_info = display_user_info(silent=True)
            nickname = user_info.get('nickname') or '匿名用户'
            vip_status = '\x1b[33m黑胶VIP\x1b[32m' if user_info.get('vip') else '\x1b[0m\x1b[2m普通用户，下载可能受限\x1b[32m'
            print(f'\n\x1b[32m欢迎，\x1b[33m{nickname}\x1b[32m！{vip_status}\x1b[0m' if not display_only else f'\n\x1b[32m用户名：\x1b[33m{nickname}\x1b[32m，{vip_status}\x1b[0m')
            print('\x1b[31m获取用户信息时实际失败！您可能无法使用任何功能！\x1b[0m' if user_info.get('user_id') is None else '')
            terminal_width, _ = get_terminal_size()
            print('\x1b[2m' + '=' * terminal_width + '\x1b[0m')
            dp = config['download_path']
            path_str = f'\x1b[36m默认（{dp}）\x1b[0m' if dp == default_path else f'\x1b[32m{dp}\x1b[0m'
            print(f'\x1b[36m[0]\x1b[0m下载位置：{path_str}')
            print('\x1b[2m' + '=' * terminal_width + '\x1b[0m')
            selected_color = '33'
            unselected_color = '2;9'
            p_lbl = color_text('歌单', selected_color if config['mode'] == 'playlist' else unselected_color)
            t_lbl = color_text('单曲', selected_color if config['mode'] == 'track' else unselected_color)
            id_val = config['playlist_id'] if config['mode'] == 'playlist' else config['track_id']
            id_title = '歌单ID' if config['mode'] == 'playlist' else '单曲ID'
            id_show = id_val if id_val else color_text('\x1b[5m[未指定]\x1b[0m', '31')
            print(f'\x1b[36m[1]\x1b[0m尝试下载 {p_lbl}{t_lbl}  \x1b[2m|\x1b[0m \x1b[36m[2]\x1b[0m{id_title}:\x1b[33m{id_show}\x1b[0m')
            print('\x1b[2m' + '-' * terminal_width + '\x1b[0m')
            if config['mode'] == 'track':
                print('单曲详细信息: ' if config['track_id'] else '详细信息:')
                if config['track_id'] and preview_cache['track']['id'] == config['track_id'] and (not preview_cache['track']['error']):
                    print(f"歌名：\x1b[36m{preview_cache['track'].get('name') or ''}\x1b[0m")
                    print(f"歌手：\x1b[36m{preview_cache['track'].get('artist') or ''}\x1b[0m")
                    ready_to_go = True
                elif config['track_id'] and preview_cache['track']['error']:
                    print(color_text(f"获取单曲信息失败：{preview_cache['track']['error']}，无法下载！", '31;5'))
                    print('')
                    ready_to_go = False
                else:
                    print(color_text(f'请先按[2]，指定要下载的曲目ID！', '31;5'))
                    print('')
                    ready_to_go = False
            else:
                print('歌单详细信息: ' if config['playlist_id'] else '详细信息: ')
                if config['playlist_id'] and preview_cache['playlist']['id'] == config['playlist_id'] and (not preview_cache['playlist']['error']):
                    if DEBUG:
                        print(f"调试信息：\x1b[90m{preview_cache['playlist']}\x1b[0m")
                    name = preview_cache['playlist'].get('name') or ''
                    count = preview_cache['playlist'].get('count')
                    print(f"曲目数：\x1b[36m{(count if count is not None else '')}\x1b[0m")
                    print(f'第一首：\x1b[36m{name}\x1b[0m')
                    ready_to_go = True
                elif config['playlist_id'] and preview_cache['playlist']['error']:
                    print(color_text(f"获取歌单信息失败：{preview_cache['playlist']['error']}，无法下载！", '31;5'))
                    print('')
                    ready_to_go = False
                else:
                    print(color_text(f'请先按[2]，指定要下载的歌单ID！', '31;5'))
                    print('')
                    ready_to_go = False
            print('\n' if display_only else '\x1b[32m准备就绪，可以下载。\n\x1b[0m' if ready_to_go else '\n', end='')
            print('\x1b[2m' + '=' * terminal_width + '\x1b[0m')
            print('下载选项\n' if not display_only else '', end='')
            print('\x1b[2m' + '-' * terminal_width + '\x1b[0m\n' if not display_only else '', end='')
            level_zh = {'standard': '标准', 'exhigh': '极高', 'lossless': '无损', 'hires': '高解析度无损', 'jymaster': '高清臻音'}.get(config['level'], config['level'])
            print(f'\x1b[36m[3]\x1b[0m音质: \x1b[33m{level_zh}\x1b[0m')
            lyrics_zh = {'both': '写入标签和文件', 'metadata': '只写入标签', 'lrc': '只写入lrc文件', 'none': '不处理歌词'}.get(config['lyrics_option'], config['lyrics_option'])
            print(f'\x1b[36m[4]\x1b[0m歌词: \x1b[33m{lyrics_zh}\x1b[0m')
            print('\x1b[2m' + '-' * terminal_width + '\x1b[0m')
            if not display_only:
                print('\x1b[42;97;1;5m[9] ▶ 开始任务\x1b[0m\t[Ctrl + C] 退出程序' if ready_to_go else '\x1b[9m[9] ▶ 开始任务\x1b[0m\t[Ctrl + C] 退出程序')
                print('\n\n键入执行操作的序号，按回车确认\x1b[36m > \x1b[0m', end='')
            return ready_to_go
        while True:
            ready_to_go = render_menu()
            choice = input().strip()
            if choice == '0':
                set_download_path()
            elif choice == '1':
                toggle_mode()
            elif choice == '2':
                input_id_for_mode()
            elif choice == '3':
                choose_level()
            elif choice == '4':
                choose_lyrics()
            elif choice == '9':
                selected_id = config['playlist_id'] if config['mode'] == 'playlist' else config['track_id']
                if not selected_id:
                    print(color_text('× 未指定ID，请先通过[2]设置。', '31'))
                    time.sleep(2)
                    continue
                if not ready_to_go:
                    print(color_text('× 当前配置无法下载，请检查错误信息，或报告给开发者。', '31'))
                    time.sleep(2)
                    continue
                render_menu(display_only=True)
                print(f'\x1b[0m\n' + '=' * terminal_width + '\n\x1b[94m  开始下载...\n\x1b[32m✓ 正在使用听歌API，不消耗VIP下载额度\x1b[0m\x1b[?25l')
                globals()['lyrics_option'] = config['lyrics_option']
                if config['mode'] == 'playlist':
                    get_playlist_tracks_and_save_info(selected_id, config['level'], config['download_path'])
                else:
                    get_track_info(selected_id, config['level'], config['download_path'])
                print('\x1b[?25h', end='')
                print('\n\x1b[32m✓ 下载任务已完成！\x1b[0m')
                with suppress(Exception):
                    send_notification('下载已完成！', f'歌曲已保存到 {config.get("download_path", "downloads")}')
                
                continue_prompt = input('\x1b[33m  按回车键返回主菜单，按\x1b[31m Ctrl + C \x1b[33m退出程序。\x1b[0m')
            else:
                pass
    except KeyboardInterrupt:
        print('\x1b[?25h', end='')
        print('\n\n\x1b[33m× 操作已被用户取消（按下了Ctrl + C组合键）。\x1b[0m')
        
    except Exception as e:
        print(f'\x1b[31m× 出现全局错误: {e}\x1b[0m')
        print('  请报告给开发者以便修复。')
    finally:
        print('\x1b[?25h', end='')
        try:
            resp = input('\x1b[33m  按回车键退出，按\x1b[31m 9 \x1b[33m并回车删除已保存会话文件并退出：\x1b[0m').strip()
            if resp == '9':
                removed = []
                for fn in ('session.json', 'session2.json'):
                    with suppress(Exception):
                        if os.path.exists(fn):
                            os.remove(fn)
                            removed.append(fn)
                if removed:
                    print('\x1b[32m✓ 已删除会话文件：' + ', '.join(removed) + '\x1b[0m')
                else:
                    print('\x1b[33m! 未找到任何会话文件可删除。\x1b[0m')
        except Exception as e:
            print(f'\x1b[31m! 退出时发生错误: {e}\x1b[0m')
        finally:
            # 保证光标可见
            print('\x1b[?25h', end='')
            