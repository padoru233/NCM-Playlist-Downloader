# 网易云歌单下载  
  
## 介绍  
  
获取网易云歌单并批量下载极高/无损/高清音质  
登录方式多样，支持扫码登录，关联登录
不消耗网易云音乐的下载次数，支持无损音质 FLAC 下载  
可同步下载歌词（包括翻译）和元数据  
只需扫码登录，粘贴音乐分享链接即可下载  


## 使用方法





确保你已经安装了`git` `python-3.6`以上版本，然后运行以下命令  

### 下载并运行
[![Code download](https://img.shields.io/badge/Code-Download-green?logo=Github)](https://github.com/padoru233/NCM-Playlist-Downloader/archive/refs/heads/main.zip)

### PIP 安装

运行终端，输入以下命令：

```bash
pip install git+https://github.com/padoru233/NCM-Playlist-Downloader.git
ncmdl
```

此后即可通过命令 `ncmdl` 运行程序。

#### 卸载
```bash
python3 -m pip uninstall -y ncm-playlist-downloader --break-system-packages
```


### 手动 live 运行
```bash
git clone https://github.com/padoru233/NCM-Playlist-Downloader.git
cd NCM-Playlist-Downloader
pip install -r requirements.txt
python script.py
```

#### Windows 
此方法使用虚拟环境，对设备影响更小    

```powershell
git clone https://github.com/padoru233/NCM-Playlist-Downloader.git
cd NCM-Playlist-Downloader
.\run.bat
```

#### Linux / Android Termux

```bash
git clone https://github.com/padoru233/NCM-Playlist-Downloader.git
cd NCM-Playlist-Downloader
chmod +x run.sh
./run.sh
```

---

- 运行程序后，选择登录方式（首选三方登录，推荐扫码登录）。
  > 若提示 `8821` 错误，可能是由于您的账号存在异常登录行为，请尝试更换登录方式（如导入已有cookie或通过兼容平台获取凭据）或等待到次日再试。
- 登录成功后，界面会提示你调整需要的选项。
- 获取歌单 ID：在歌单页面选择“分享”，复制类似 https://music.163.com/m/playlist?id=12345678 的链接（链接中 playlist?id= 后面的数字就是歌单 ID），将其粘贴到程序中并按回车。
- 下载单曲：方式类似，获取单曲链接并粘贴（若只有ID则需要手动切换尝试下载）
- 选择需要的音质和歌词处理方式等选项。
- 确认显示信息无误后，输入数字 9 并按回车开始下载。

## 说明

### 音质说明

- 标准`standard`
    - mp3格式 普通音质 ~128kbps
    - 声道: 立体声 stereo
    - 采样率: 44100 Hz
    - 位每采样: 32
    - 编解码器: MPEG Audio layer 1/2 (mpga)
    ```
    Stream #0:0: Audio: mp3 (mp3float), 44100 Hz, stereo, fltp, 128 kb/s
      Metadata:
        encoder         : Lavc58.13
    ```
    - 通常一首歌大小3-5MB左右

- **极高`exhigh` (HQ)**
    - mp3格式 近CD品质 最高320kbps
    - 声道: 立体声 stereo
    - 采样率: 44100 Hz
    - 位每采样: 32
    - 编解码器: MPEG Audio layer 1/2 (mpga)
    ```
    Stream #0:0: Audio: mp3 (mp3float), 44100 Hz, stereo, fltp, 320 kb/s
      Metadata:
        encoder         : Lavc58.13
    ```
    - 通常一首歌大小8-10MB左右

- 无损`lossless` (SQ VIP)
    - flac格式 高保真无损音质 最高48KHz/16bit
    - 声道: 立体声 stereo
    - 采样率: 44100 Hz
    - 位每采样: 32
    - 编解码器: FLAC (Free Lossless Audio Codec) (flac)
    ```
      Stream #0:0: Audio: flac, 44100 Hz, stereo, s16
    ```
    - 通常一首歌大小25-30MB左右
    - 需要 VIP 账号
    - flac格式 高保真无损音质 最高48KHz/16bit
    - 声道: 立体声 stereo
    - 采样率: 44100 Hz
    - 位每采样: 32
    - 编解码器: FLAC (Free Lossless Audio Codec) (flac)
    ```
      Stream #0:0: Audio: flac, 44100 Hz, stereo, s16
    ```
    - 通常一首歌大小25-30MB左右
    - 需要 VIP 账号

- 高解析度无损`hires` (Spatial Audio VIP)
    - flac格式 更饱满清晰的高解析度音质 最高192kHz/24bit
    - 声道: 立体声 stereo
    - 采样率: 44100 Hz
    - 位每采样: 32
    - 编解码器: FLAC (Free Lossless Audio Codec) (flac)
    ```  
    Stream #0:0: Audio: flac, 44100 Hz, stereo, s16
    ```
    - 通常一首歌大小50MB左右
    - 需要 VIP 账号

- 高清臻音`jymaster` (Master VIP)
    - flac格式 声音听感增强 96kHz/24bit
    - 声道: 立体声 stereo
    - 采样率: 96000 Hz
    - 位每采样: 32
    - 编解码器: FLAC (Free Lossless Audio Codec) (flac)
    ```
      Stream #0:0: Audio: flac, 96000 Hz, stereo, s32 (24 bit)
    ```
    - 通常一首歌大小150MB左右
    - 需要 VIP 账号
    - 
- 高清臻音`jymaster` (Master VIP)
    - flac格式 声音听感增强 96kHz/24bit
    - 声道: 立体声 stereo
    - 采样率: 96000 Hz
    - 位每采样: 32
    - 编解码器: FLAC (Free Lossless Audio Codec) (flac)
    ```
      Stream #0:0: Audio: flac, 96000 Hz, stereo, s32 (24 bit)
    ```
    - 通常一首歌大小150MB左右（**巨大！**）
    - 需要 VIP 账号

### 音频标签（元数据）

文件添加完整的元数据标签（受限于可用的API）：
- 歌曲标题`TITLE`
- 艺术家信息`ARTIST`
- 专辑名称`ALBUM`
- 曲目轨道编号`track`
- 发行年份`DATE`
- 专辑封面图片`COVER`
- 歌词（如果选择嵌入）`LYRICS`

支持MP3(ID3标签)和FLAC格式的元数据嵌入，使音乐文件在各类播放器中显示完整信息。

### 歌词

程序提供多种歌词处理方式，在下载时可选择：
- `lrc`：保存为独立LRC文件（与音频文件同名），UTF-8编码
- `metadata`：将歌词嵌入到音频文件元数据中
- `both`：同时保存独立文件和嵌入元数据
- `none`：不下载歌词

默认设置为保存独立LRC文件。

#### 歌词翻译处理

当歌词有翻译版本时，程序会处理翻译内容：
1. 解析原文和翻译歌词的时间轴
2. 将翻译行插入到对应原文行之后
3. 优化翻译行时间戳，使播放时原文与翻译依次显示
4. 导出为标准LRC格式，兼容大多数音乐播放器

示例：
```lyric
[01:01.57]I’m covering my ears like a kid
[01:04.81]我像孩子一样堵住耳朵
[01:04.82]When your words mean nothing, I go la la la
[01:09.17]当你的话语毫无意义时 我就高唱 啦啦啦
[01:09.18]I’m turning off the volume when you speak
...
```
显示效果：

---
I’m covering my ears like a kid <br>
我像孩子一样堵住耳朵<br>
**When your words mean nothing, I go la la la**<br>
当你的话语毫无意义时 我就高唱 啦啦啦 *（译文不会被播放器聚焦）*<br> 
I’m turning off the volume when you speak<br>

---
使得歌词在播放时，高亮原文，翻译位于原文下方，像在线播放格式一样。

### 文件说明

- `session.json`：
  保存登录会话信息的文件，使您下次使用时无需重新登录。
  包含加密的用户凭证，仅保存在本地。

- `ncm.png`：
  登录时生成的二维码图片文件，用于网易云音乐APP扫码登录。
  登录完成后可以删除。

- `downloads/`：
  默认的下载目录，所有音乐和歌词文件将保存在此。
  可在运行程序时自定义下载路径。

- `!#_playlist_{playlist_id}_info.txt`：
  保存歌单信息的文本文件，包含歌单中所有歌曲的ID、名称和艺术家。
  便于查找特定歌曲和记录歌单内容。

- `!#_FAILED_LIST.txt`：
  记录下载失败的歌曲列表，包含歌曲ID、名称、艺术家和失败原因。  
  常见失败原因包括：歌曲已下架、地区限制、单曲付费、VIP权限不足等。  

## 测试

克隆本项目后，创建虚拟环境并安装依赖`requirements.txt`和`pytest`，然后运行下列命令以执行单元测试  
```
python -m pytest tests/test_script.py -q
```

## 鸣谢
- [pyncm](https://github.com/mos9527/pyncm)





