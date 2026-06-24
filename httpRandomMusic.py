# coding=utf-8
# HTTP随机音乐播放器
# 给小爱音箱用于播放NAS音乐

import os
import random
import urllib.parse
import posixpath
import shutil
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

# 端口号
port = 8080

# 音乐目录
fileDir = '/volume1/music/github'

# ffmpeg路径，留空则不转码
ffmpeg = '/usr/bin/ffmpeg'

fileList = []
fileIndex = 0

# 播放列表请求计数
playlist_request_count = 0


def updateFileList():
    global fileList
    global fileIndex

    if not os.path.exists(fileDir):
        print("ERROR: 请检查目录是否存在")
        exit()

    fileIndex = 0

    support_ext = ('.flac', '.mp3', '.wav', '.aac', '.m4a')

    fileList = [
        os.path.relpath(os.path.join(root, f), fileDir).replace('\\', '/')
        for root, _, files in os.walk(fileDir)
        for f in files
        if f.lower().endswith(support_ext)
    ]

    # 按修改时间排序（最新优先）
    fileList.sort(
        key=lambda x: os.path.getmtime(os.path.join(fileDir, x)),
        reverse=True
    )

    print(f'{len(fileList)} files')


class meHandler(BaseHTTPRequestHandler):

    def translate_path(self, path):
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]

        trailing_slash = path.rstrip().endswith('/')

        try:
            path = urllib.parse.unquote(path, errors='surrogatepass')
        except UnicodeDecodeError:
            path = urllib.parse.unquote(path)

        path = posixpath.normpath(path)

        words = filter(None, path.split('/'))

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

        # 没有歌曲时刷新一次
        if len(fileList) == 0:
            updateFileList()

        if len(fileList) == 0:
            self.send_response(404)
            self.end_headers()
            self.wfile.write("No music files found".encode())
            return

        # 顺序播放
        if self.path == '/':
            self.return302(fileList[fileIndex])

            fileIndex += 1
            if fileIndex >= len(fileList):
                fileIndex = 0

        # 随机播放
        elif self.path == '/random':
            updateFileList()
            random.shuffle(fileList)
            self.return302(fileList[0])
            fileIndex = 1

        # 第一首
        elif self.path == '/first':
            updateFileList()
            self.return302(fileList[0])
            fileIndex = 1

        # m3u8播放列表
        elif self.path == '/playlist':

            playlist_request_count += 1

            if playlist_request_count <= 10:

                updateFileList()
                random.shuffle(fileList)

                self.send_response(200)
                self.send_header(
                    "Content-type",
                    "application/vnd.apple.mpegurl"
                )
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()

                m3u8_content = "#EXTM3U\n"
                m3u8_content += "#EXT-X-VERSION:3\n"
                m3u8_content += "#EXT-X-ALLOW-CACHE:NO\n"
                m3u8_content += "#EXT-X-TARGETDURATION:3\n"

                for file_name in fileList:
                    m3u8_content += (
                        "#EXTINF:3.000,\n"
                        + urllib.parse.quote(file_name)
                        + "\n"
                    )

                m3u8_content += "#EXT-X-ENDLIST\n"

                self.wfile.write(m3u8_content.encode())

            else:
                self.send_response(500)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(
                    "Too many playlist requests".encode()
                )

        # 播放文件
        else:
            path = self.translate_path(self.path)

            print(path)

            if os.path.isfile(path):

                self.send_response(200)

                # 转码成wav
                if ffmpeg and path.lower().split('.')[-1] != 'wav':

                    self.send_header("Content-type", "audio/wav")
                    self.send_header("Accept-Ranges", "none")
                    self.end_headers()

                    try:
                        pipe = subprocess.Popen(
                            [
                                ffmpeg,
                                '-i',
                                path,
                                '-f',
                                'wav',
                                '-'
                            ],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            bufsize=10 ** 8
                        )

                        shutil.copyfileobj(pipe.stdout, self.wfile)

                    finally:
                        self.wfile.flush()
                        pipe.terminate()

                # 原始文件输出
                else:

                    self.send_header("Content-type", "audio/mpeg")
                    self.send_header("Accept-Ranges", "none")

                    with open(path, 'rb') as f:
                        self.send_header(
                            "Content-Length",
                            str(os.fstat(f.fileno()).st_size)
                        )
                        self.end_headers()

                        shutil.copyfileobj(f, self.wfile)

            else:
                self.send_response(404)
                self.end_headers()


if __name__ == '__main__':
    updateFileList()

    print(f"HTTP随机音乐服务器启动")
    print(f"监听端口: {port}")
    print(f"音乐目录: {fileDir}")

    HTTPServer(("", port), meHandler).serve_forever()
