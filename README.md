# Xiaoai_PlayLocal
让小爱同学播放本地/远程歌曲的方案 | 小爱音箱播放本地歌曲




> 环境：HACS+Python
> 问题：小爱同学不能播放本地歌曲或者群晖中的歌曲
> 解决办法：HACS + Http Server

   
> 背景：冲绿砖是不可能的，DLNA也被阉割了，只能曲线救国了

> 解决思路：通过HACS监控小爱事件，推送媒体链接并随机播放，具体看下面的流程图
![在这里插入图片描述](https://img-blog.csdnimg.cn/50fcfa812b294ed8a873d68f0f8cfcd7.png)

@[TOC](文章目录)

---

## 1.安装HACS：
步骤略，自行解决，我是在群晖上拉的官方容器 homeassistant/home-assistant:latest



## 2.安装HACS 小米集成：

步骤略，自行解决，我是在集成中搜索添加的，参考下图，确保音箱出现：

![在这里插入图片描述](https://img-blog.csdnimg.cn/2ee3b061291143d4929b2b82def33c31.png)


## 3.调试音乐播放
### 3.1 在HACS开发者工具中调试音乐播放
参考下图，准备一个mp3的url链接，最好是直连，重定向的我测试也可以

步骤：开发者工具-服务器-play media-选择实体-ID为链接地址，选择播放

如果一切顺利的话，你会听到小爱音箱直接播放音乐，你已经成功90%了

![在这里插入图片描述](https://img-blog.csdnimg.cn/b4677370da1a46b2a06e6607ca599f74.png)

### 3.2 构建随机播放列表
我们的目的是让小爱播放我们服务器中的所有音乐，只推送一个MP3链接是不行的
这一块我尝试了很多方法，最后的思路是用python 写一个http的服务器：
1.当用户请求/playlist时立即扫描本地音频文件
2.打乱文件顺序，生成一个m3u8的播放列
3.小爱读取播放列表的音频地址，向服务器请求
3.服务器将不是WAV格式的音频转码给小爱播放，这样flac格式或者大容量MP3文件播放不会卡顿

直接上代码：


```
# coding=utf-8

# http随机音乐播放器
# 给小爱音箱用于播放nas的音乐

import os, random, urllib, posixpath, shutil, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

# 端口号
port = 8080

# 存音乐的目录
fileDir = '/volume1/music/'

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

```

### 3.3 测试播放列表
1.将python代码保存为musicServerForXioai.py, 启动运行
2.访问http://你的IP地址:8080/playlist，你会得到一个,3u8的文件，反复测试多次，每次下载的播放列表歌曲顺序都不一样
3.使用IINA播放器等支出m3u8格式的播放器，打开url，音乐会开始播放，音频时长一直在增加



## 4.编写 HACS时间

### 4.1 在HACS中设置场景自动化
假设我们触发的命名是：小爱同学，播放服务器上的音乐
我们用HACS查询小爱的聊天记录，查询到了我们的关键词，就触发播放媒体的命令

在HACS 场景自动化中新建一条：

![在这里插入图片描述](https://img-blog.csdnimg.cn/42d64e827da14cafbc50269f37c81f5e.png)
参开代码，自行修改，或者按上图在图形化界面中设置

![在这里插入图片描述](https://img-blog.csdnimg.cn/369a67f7e26d45fcacb886e6ab5c6c68.png)
![在这里插入图片描述](https://img-blog.csdnimg.cn/d8d2a4a1bee44434bf441a8120859989.png)


```
alias: 小爱2
description: ""
trigger:
  - platform: state
    entity_id:
      - sensor.xiaomi_lx5a_ed78_conversation
    attribute: content
    to: 播放服务器上的音乐
  - platform: state
    entity_id:
      - sensor.xiaomi_lx5a_ed78_conversation
    attribute: content
    to: 播放服务器上的歌曲
condition: []
action:
  - device_id: d17e92cedd00f3233f35281579b3ebfb
    domain: text
    entity_id: text.xiaomi_lx5a_ed78_execute_text_directive
    type: set_value
    value: 暂停
  - service: media_player.play_media
    data:
      media_content_id: http://IP:端口/playlist
      media_content_type: music
      enqueue: add
      extra:
        thumb: https://brands.home-assistant.io/_/homeassistant/logo.png
        title: NAS上的歌曲
    target:
      entity_id: media_player.xiaomi_lx5a_ed78_play_control
mode: single

```

### 4.2 测试小爱
至此全部完成了，我们对小爱说：播放服务器上的音乐，观察下HACS的日志，开始享受吧


![在这里插入图片描述](https://img-blog.csdnimg.cn/0fe88038953046c78122ba048414867b.png)



 




参考引用：[https://github.com/wangrui1573/Xiaoai_PlayLocal](https://github.com/wangrui1573/Xiaoai_PlayLocal)

