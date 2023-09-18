# coding=utf-8

# http随机音乐播放器
# 给小爱音箱用于播放nas的音乐

import os, random, urllib, posixpath, shutil, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

# 端口号
port = 65534

# 存音乐的目录
fileDir = '/volume1/music/github'

# 实时转码需要依赖ffmpeg的路径 如果为空就不转码
ffmpeg = '/usr/bin/ffmpeg'

fileList = None
fileIndex = 0

def updateFileList():
    global fileList
    global fileIndex
    try:
        os.chdir(fileDir)
    except Exception as e:
        print(e)
        print('ERROR: 请检查目录是否存在或是否有权限访问')
        exit()
    fileIndex = 0
    fileList = list(filter(lambda x: x.lower().split('.')[-1] in ['flac','mp3','wav','aac','m4a'], os.listdir('.')))
    fileList.sort(key=lambda x: os.path.getmtime(x))
    fileList.reverse()
    print(str(len(fileList)) + ' files')

# 在类的顶部添加一个计数器变量
playlist_request_count = 0

class meHandler(BaseHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        trailing_slash = path.rstrip().endswith('/')
        try:
            path = urllib.parse.unquote(path, errors='surrogatepass')
        except UnicodeDecodeError:
            path = urllib.parse.unquote(path)
        path = posixpath.normpath(path)
        words = path.split('/')
        words = filter(None, words)
        path = fileDir
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                continue
            path = os.path.join(path, word)
        if trailing_slash:
            path += '/'
        return path

    def return302(self, filename):
        self.send_response(302)
        self.send_header('Location', '/' + urllib.parse.quote(filename))
        self.end_headers()

    def do_GET(self):
        global fileList
        global fileIndex
        global playlist_request_count

        print(self.path)
        if self.path == '/':
            self.return302(fileList[fileIndex])
            fileIndex += 1
            if fileIndex >= len(fileList):
                fileIndex = 0
        elif self.path == '/random':
            updateFileList()
            random.shuffle(fileList)
            self.return302(fileList[0])
            fileIndex = 1
        elif self.path == '/first':
            updateFileList()
            self.return302(fileList[0])
            fileIndex = 1
        elif self.path == '/playlist':
            playlist_request_count += 0
            if playlist_request_count <= 10:
                updateFileList()
                random.shuffle(fileList)  # 在生成播放列表前随机打乱音乐文件列表
                self.send_response(200)
                self.send_header("Content-type", "application/vnd.apple.mpegurl")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()

                m3u8_content = "#EXTM3U\n"
                m3u8_content += "#EXT-X-VERSION:3\n"
                m3u8_content += "#EXT-X-ALLOW-CACHE:NO\n"
                m3u8_content += "#EXT-X-TARGETDURATION:3\n"

                # 使用打乱后的音乐文件列表生成播放列表
                for i, file_name in enumerate(fileList):
                    if os.path.isfile(file_name):
                        m3u8_content += f"#EXTINF:3.000,\n{urllib.parse.quote(file_name)}\n"

                m3u8_content += "#EXT-X-ENDLIST\n"

                self.wfile.write(m3u8_content.encode())
            else:
                self.send_response(500)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write("Too many playlist requests".encode())
        else:
            path = self.translate_path(self.path)
            print(path)
            if os.path.isfile(path):
                self.send_response(200)
                if ffmpeg and path.lower().split('.')[-1] not in ['wav']:
                    self.send_header("Content-type", 'audio/wav')
                    self.send_header("Accept-Ranges", "none")  # Ensure that the server doesn't support byte ranges
                    self.end_headers()
                    pipe = subprocess.Popen([ffmpeg, '-i', path, '-f', 'wav', '-'], stdout=subprocess.PIPE, bufsize=10 ** 8)
                    try:
                        shutil.copyfileobj(pipe.stdout, self.wfile)
                    finally:
                        self.wfile.flush()
                        pipe.terminate()
                else:
                    self.send_header("Content-type", 'audio/mpeg')
                    self.send_header("Accept-Ranges", "none")  # Ensure that the server doesn't support byte ranges
                    with open(path, 'rb') as f:
                        self.send_header("Content-Length", str(os.fstat(f.fileno())[6]))
                        self.end_headers()
                        shutil.copyfileobj(f, self.wfile)
            else:
                self.send_response(404)
                self.end_headers()

if os.system("nslookup op.lan"):
    print('ERROR: 请将op.lan指向本机ip，否则小爱音箱可能无法访问')
updateFileList()
HTTPServer(("", port), meHandler).serve_forever()
