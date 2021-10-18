"""Authentication for Fava, with encrypted storage"""
# This application is meant to be used alongside nginx to authenticate a Fava session
# Once authenticated, a securefs path will be mounted/decrypted, and Fava will be able
# To parse the beancount files within.
# After the seesion has been idel for 10 minutes, securefs will shutdown and the drive
# will be inaccessible
# The authentication works as follows:
# 1) Run <script> generate to generate a secure key
#    This will ask for the securefs password as well as the web passord to use
#    The web-password is converted ito a fernet key, and used to encrypt the securefs password
#    The output will be a Fernet encrypted message that is stored in 'auth.token'
# 2) On login the password is converted into the fernet key and used to decrypt the securefs password
#    If the login is successful, the fernet key is re-encrypted using an local key, and stored as a cookie with a 24hr lifetime
# 3) For subsequent access, the cookie is descrypted using the local key.
#    This process uses a TTL, such that even if the cookie lifetime is manipulated, a password is needed every 24 hours
#    If needed, the cookie can be used to re-start the securefs process.
# 4) The securefs process will be terminated after 10 minutes of no activity (note that the polled 'changed' requests are ignored for this decision

import os
import asyncio
import argparse
import sys
import time
import hashlib
import logging
import base64
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logging.basicConfig(format='%(asctime)s %(levelname)-10s %(message)s', level=logging.INFO, datefmt='%Y-%m-%dT%H:%M:%S')
try:
    from aiohttp import web, ClientSession
    routes = web.RouteTableDef()
except:
    logging.warning("aiohttp module could not be loaded.  Only password-creation is supported")
    # Hack to bypass route decorators
    routes = type("Route", (object,), {
      'get':  lambda url: lambda func: lambda *args, **kwargs: func(*args, **kwargs),
      'post': lambda url: lambda func: lambda *args, **kwargs: func(*args, **kwargs),
    })

logging.getLogger('aiohttp.access').setLevel(logging.WARNING)  # silence aiohttp info messages

BASE_DIR = os.path.dirname(__file__)
SECUREFS = "securefs"
ENCRYPTED_DIR = os.path.join(BASE_DIR, "secure")
DECRYPTED_DIR = os.path.join(BASE_DIR, "ledger")
TEST_FILE = ".encrypted"
SECUREFS_STARTUP_TIMEOUT = 10
SECUREFS_LIFETIME = 10 * 60
COOKIE_LIFETIME = 24 * 3600
COOKIE_KEY = Fernet(b'kh44idAzyc4YGpnns2WWw_ewlsS3aA3PSrip8ToRVQ0=')

LOGIN = {
    'token': None,
    'poll': None,
    'expire': 0,
    'securefs': None,
    }

def cipherFernet(password):
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b'abcd', iterations=1000, backend=default_backend()).derive(password.encode('utf8'))
    return base64.urlsafe_b64encode(key)

def encrypt1(plaintext, password):
    return Fernet(cipherFernet(password)).encrypt(plaintext)

def decrypt1(ciphertext, password):
    return Fernet(cipherFernet(password)).decrypt(ciphertext)

def read_tokens(token_file):
    with open(token_file, 'rb') as _fh:
        data = _fh.read()
        try:
            cookie_key, securefs = data.split(b'\0')
            return cookie_key, securefs
        except Exception:
            return None, None

async def test_expire():
    while True:
        if LOGIN['securefs'] and time.time() > LOGIN['expire']:
            logging.warning("Expiring")
            proc = LOGIN['securefs']
            try:
                proc.terminate()
                await proc.wait()
            except Exception as _e:
                logging.error("Got unexpected error while terminating encryption for pid %s: %s", proc.pid, _e)
            LOGIN['securefs'] = None
            LOGIN['expire'] = 0
            LOGIN['poll'] = None
            logging.warning("Expired")
            break
        logging.info("%d seconds left.  Trying again in 30 secs", LOGIN['expire'] - time.time())
        await asyncio.sleep(30)

async def login(key):
    _f = Fernet(key)
    try:
        secure_pw = _f.decrypt(LOGIN['token'])
    except InvalidToken:
        logging.warning("Key '%s' is invalid", key)
        return False
    #proc = await asyncio.create_subprocess_exec(SECUREFS, "m", ENCRYPTED_DIR, DECRYPTED_DIR, "-o", "ro,nonempty", stdin=asyncio.subprocess.PIPE)
    proc = await asyncio.create_subprocess_exec(SECUREFS, "m", LOGIN['ENCRYPTED_DIR'], LOGIN['DECRYPTED_DIR'],
                                                "--pass", secure_pw, "-o", "nonempty")
    #proc.stdin.write(secure_pw)
    #await proc.stdin.drain()
    timeout = time.time() + SECUREFS_STARTUP_TIMEOUT
    while proc.returncode is None and not os.path.exists(LOGIN['TEST_FILE']) and time.time() < timeout:
        await asyncio.sleep(0.1)
    if proc.returncode:
        logging.error("Failed to decrypt %s: exit_code: %d", LOGIN['ENCRYPTED_DIR'], proc.returncode)
        return False
    logging.warning("Checking for: %s", LOGIN['TEST_FILE'])
    if os.path.exists(LOGIN['TEST_FILE']):
        change_url = LOGIN.get('CHANGE_URL')
        if change_url:
            async with ClientSession() as client:
                async with client.get(change_url) as resp:
                    await resp.text()
        LOGIN['securefs'] = proc
        LOGIN['expire'] = time.time() + LOGIN['SECUREFS_LIFETIME']
        if not LOGIN['poll']:
            LOGIN['poll'] = asyncio.create_task(test_expire())
        return True
    logging.error("Failed to decrypt %s (pid: %s)", proc.pid, LOGIN['ENCRYPTED_DIR'])
    try:
        proc.terminate()
        await proc.wait()
    except:
        pass
    return False
    

@routes.get('/login')
async def get_login(request, target=None):
    logging.warning("Got 'GET' request for /login headers: %s", request.headers)
    if target is None:
        target = request.headers.get('X-Target')
        show_error = '0'
    else:
        show_error = '1'

    if target is None:
        logging.error('target url is not passed')
        raise web.HTTPInternalServerError()
    html="""
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<html>
  <head>
    <meta http-equiv=Content-Type content="text/html;charset=UTF-8">
    <title>Beancount Login</title>
<style>
html {
  height: 100%;
}

body {
  height: 100%;
  margin: 0;
  font-family: Arial, Helvetica, sans-serif;
  display: grid;
  justify-items: center;
  align-items: center;
  background-color: #3a3a3a;
}

#main-holder {
  width: 50%;
  height: 70%;
  display: grid;
  justify-items: center;
  align-items: center;
  background-color: white;
  border-radius: 7px;
  box-shadow: 0px 0px 5px 2px black;
}

#login-error-msg-holder {
  width: 100%;
  height: 100%;
  display: grid;
  justify-items: center;
  align-items: center;
}

#login-error-msg {
  width: 23%;
  text-align: center;
  margin: 0;
  padding: 5px;
  font-size: 12px;
  font-weight: bold;
  color: #8a0000;
  border: 1px solid #8a0000;
  background-color: #e58f8f;
  opacity: SHOW_ERROR;
}

#error-msg-second-line {
  display: block;
}

#login-form {
  align-self: flex-start;
  display: grid;
  justify-items: center;
  align-items: center;
}
label {
    color: #555;
    display: inline-block;
    padding-top: 10px;
    font-size: 14px;
}

input {
    font-family: "Helvetica Neue", Helvetica, sans-serif;
    font-size: 12px;
    outline: none;
}
input[type=text],
input[type=password] {
    color: #777;
    padding-left: 10px;
    margin: 10px;
    margin-top: 12px;
    margin-left: 18px;
    width: 290px;
    height: 35px;
        border: 1px solid #c7d0d2;
    border-radius: 2px;
    box-shadow: inset 0 1.5px 3px rgba(190, 190, 190, .4), 0 0 0 5px #f5f7f8;
-webkit-transition: all .4s ease;
    -moz-transition: all .4s ease;
    transition: all .4s ease;
        }
input[type=text]:hover,
input[type=password]:hover {
    border: 1px solid #b6bfc0;
    box-shadow: inset 0 1.5px 3px rgba(190, 190, 190, .7), 0 0 0 5px #f5f7f8;
}
input[type=text]:focus,
input[type=password]:focus {
    border: 1px solid #a8c9e4;
    box-shadow: inset 0 1.5px 3px rgba(190, 190, 190, .4), 0 0 0 5px #e6f2f9;
}
#lower {
    background: #ecf2f5;
    width: 100%;
    height: 69px;
    margin-top: 20px;
          box-shadow: inset 0 1px 1px #fff;
    border-radius: 2px;
    box-shadow: inset 0 1.5px 3px rgba(190, 190, 190, .4), 0 0 0 5px #f5f7f8;
}
input[type=submit] {
    justify-items: center;
    align-items: center;
    margin-right: 20px;
    margin-top: 20px;
    width: 80px;
    height: 30px;
    font-size: 14px;
    font-weight: bold;
    color: #fff;
    background-color: #acd6ef; /*IE fallback*/
    background-image: -webkit-gradient(linear, left top, left bottom, from(#acd6ef), to(#6ec2e8));
    background-image: -moz-linear-gradient(top left 90deg, #acd6ef 0%, #6ec2e8 100%);
    background-image: linear-gradient(top left 90deg, #acd6ef 0%, #6ec2e8 100%);
    border-radius: 30px;
    border: 1px solid #66add6;
    box-shadow: 0 1px 2px rgba(0, 0, 0, .3), inset 0 1px 0 rgba(255, 255, 255, .5);
    cursor: pointer;
}
input[type=submit]:hover {
    background-image: -webkit-gradient(linear, left top, left bottom, from(#b6e2ff), to(#6ec2e8));
    background-image: -moz-linear-gradient(top left 90deg, #b6e2ff 0%, #6ec2e8 100%);
    background-image: linear-gradient(top left 90deg, #b6e2ff 0%, #6ec2e8 100%);
}
input[type=submit]:active {
    background-image: -webkit-gradient(linear, left top, left bottom, from(#6ec2e8), to(#b6e2ff));
    background-image: -moz-linear-gradient(top left 90deg, #6ec2e8 0%, #b6e2ff 100%);
    background-image: linear-gradient(top left 90deg, #6ec2e8 0%, #b6e2ff 100%);
}
</style>
</style>
  </head>
  <body>
    <main id="main-holder">
    <h1 id="login-header">Beancount Login</h1>
    <div id="login-error-msg-holder">
      <p id="login-error-msg">Invalid password</p>
    </div>
    <form action="/login" method="post" id="login-form">
        <label for="password-field">Password:</label>
        <input type="password" name="password" autocomplete="current-password" id="password-field" class="login-form-field"/>
        <input type="submit" value="Login">
        <input type="hidden" name="target" value="TARGET">
    </form>
    </main>
  </body>
</html>"""
    resp = web.Response(text=html.replace('TARGET', target).replace('SHOW_ERROR', show_error), content_type='text/html')
    resp.del_cookie('auth')
    return resp

@routes.post('/login')
async def post_login(request):
    data = await request.post()
    passwd = data.get('password')
    target = data.get('target')
    if passwd and target:
        passwd = cipherFernet(passwd)
        if await login(passwd):
            logging.info("Logged in for URL: %s", target)
            resp = web.HTTPFound(location='/')  #target
            cookie = LOGIN['COOKIE_KEY'].encrypt(passwd).decode('utf8')
            print(cookie)
            resp.set_cookie("auth", cookie, httponly=True, samesite="Strict", max_age=COOKIE_LIFETIME)
            return resp
    return await get_login(request, target=target)

@routes.get('/auth-proxy')
async def get_auth_proxy(request):
    if not request.headers.get('X-Original-URI', '').endswith('/api/changed'):
        logging.info("Got 'GET' request for /auth-proxy: %s %s", request.url, request.headers.get('X-Original-URI'))
    fail = web.HTTPUnauthorized(headers={'WWW-Authenticate': f'Basic realm="Restricted"', 'Cache-Control': 'no-cache'})
    fail.del_cookie('auth')
    uri =  request.headers.get('X-Original-URI')
    if not uri:
        loging.warning("Made auth request without X-Original-URI")
        raise fail
    if uri.endswith('/api/changed'):
        return web.Response(text="ok")
    auth = request.cookies.get('auth')
    if not auth:
        logging.warning("No auth specified")
        logging.warning("Got 'GET' request for /auth-proxy: %s headers: %s cookies: %s", request.url, request.headers, request.cookies)
        raise fail
    try:
        auth = LOGIN['COOKIE_KEY'].decrypt(auth.encode('utf8'), ttl=COOKIE_LIFETIME)
    except InvalidToken:
        logging.warning("Got invalid auth")
        raise fail

    if not LOGIN['securefs']:
        if not await login(auth):
            logging.warning("Login Failed")
            raise fail
    LOGIN['expire'] = time.time() + LOGIN['SECUREFS_LIFETIME']
    return web.Response(text="ok")

def generate_keys(token_file):
    import getpass
    if os.path.exists(token_file):
        cookie_key, _securefs = read_tokens(token_file)
    if not cookie_key:
        cookie_key = Fernet.generate_key()
    secure = getpass.getpass(prompt="SecureFS Password:")
    login = getpass.getpass(prompt="Login Password:")
    token = encrypt1(secure.encode('utf8'), login)
    with open(token_file, "wb") as _fh:
        _fh.write(cookie_key + b'\0')
        _fh.write(token)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--encrypted_path", help="Encrypted path")
    parser.add_argument("--decrypted_path", help="Decrypted path")
    parser.add_argument("--auth_file", default=os.path.join(BASE_DIR, "auth.token"), help="Auth file")
    parser.add_argument("--set_password", action="store_true", help="Set password")
    parser.add_argument("--change_url", help="URL to send GET request to on encryption start")
    parser.add_argument("--keep_open", type=int, default=SECUREFS_LIFETIME, help="Seconds to keep filesystem decrypted")
    parser.add_argument("--check_file", default=TEST_FILE, help="Path to file to validate decryption complete")
    parser.add_argument("--port", default=5002, type=int, help="Listening port")
    args = parser.parse_args()
    if args.set_password:
        generate_keys(args.auth_file)
        return 0
    if not args.encrypted_path or not args.decrypted_path:
        logging.error("Must specify both -encrypted_path and --decrypted_path")
        return 1
    for path in (args.encrypted_path, args.decrypted_path):
        if not os.path.exists(args.encrypted_path):
            logging.error("%s does not exist", path)
            return 1
    LOGIN['ENCRYPTED_DIR'] = args.encrypted_path
    LOGIN['DECRYPTED_DIR'] = args.decrypted_path
    LOGIN['CHANGE_URL'] = args.change_url
    LOGIN['SECUREFS_LIFETIME'] = args.keep_open
    LOGIN['TEST_FILE'] = os.path.join(LOGIN['DECRYPTED_DIR'], args.check_file)
    cookie_key, LOGIN['token'] = read_tokens(args.auth_file)
    LOGIN['COOKIE_KEY'] = Fernet(cookie_key)
    app = web.Application()
    app.add_routes(routes)
    web.run_app(app, port=args.port)

sys.exit(main())
