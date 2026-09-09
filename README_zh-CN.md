<div align="center">
  <img width="100" height="100" src="assets/icons/eye.png" alt="眨眼呼叫图标"/>
  <h1>眨眼呼叫</h1>
  <p><strong>为渐冻症患者设计：通过眨眼向家属或照护者发出声音提醒。</strong></p>
  <p>无需说话、手部动作或专用眼控设备，只需一台带摄像头的 Windows/Mac 电脑。</p>
  <p><strong>简体中文</strong> | <a href="README.md">English</a></p>
  <p>
    <a href="https://github.com/JouleEmbodiedAILab/blink-call/releases/latest"><strong>下载 Windows 版</strong></a>
    ·
    <a href="https://JouleEmbodiedAILab.github.io/blink-call/first-use/"><strong>首次使用指南</strong></a>
    ·
    <a href="https://JouleEmbodiedAILab.github.io/blink-call/"><strong>完整用户手册</strong></a>
  </p>
</div>


<video src="https://github.com/user-attachments/assets/2579037f-2dea-4fcf-aa7d-e905464cd1be" width="800" controls
  playsinline></video>

## 这款软件能做什么

当患者无法方便地说话或按下实体呼叫器时，眨眼呼叫可以通过摄像头识别预先设置好的睁眼、闭眼动作。完成整套动作后，电脑或已连接的蓝牙音箱会播放提醒声音，帮助患者呼叫身边的家属或照护者。

- **只需眨眼**：不需要说话、点击鼠标或触碰按钮。
- **普通摄像头即可使用**：支持电脑内置摄像头和 USB 摄像头，无需专用眼控设备。
- **可以按患者情况调整**：可自定义眨眼动作、铃声、音量和播放时长。
- **降低自然眨眼误触发**：通过连续的睁眼、闭眼动作组成呼叫序列。
- **公益免费**：软件完全免费使用。

## 使用前需要准备

- 一台 Windows/Mac 电脑。
- 一个能清楚拍到患者双眼的摄像头。
- 电脑扬声器或蓝牙音箱。
- 首次下载模型文件时可用的网络连接。
- 建议由家属或照护者协助完成第一次配置和测试。

> [!NOTE]
> 目前只有 Windows 版可以直接下载使用。Linux 和 macOS 用户需要按照页面底部的开发者指南从源码运行。

## 下载软件

从下面任意一个地址下载最新版本：

- [GitHub 最新版本](https://github.com/JouleEmbodiedAILab/blink-call/releases/latest)
- [百度网盘](https://pan.baidu.com/s/1Og8-TmnR_yIdsOA2_MHyiw?pwd=fk35)
- [夸克网盘](https://pan.quark.cn/s/e96254bb1153)

下载完成后，先将软件压缩包解压到一个固定位置，再双击文件夹中的 `BlinkCall.exe`。请不要直接在压缩包内运行软件。

## 第一次使用

### 1. 打开软件

双击 `BlinkCall.exe`。软件打开后，主界面会显示摄像头画面和顶部的眨眼进度条。



### 2. 下载模型文件

第一次使用时，需要先进入：

**设置 → 眨眼呼叫 → 下载/更新模型文件**

点击“下载/更新”，等待下载完成，然后保存设置并返回主界面。

### 3. 允许使用摄像头

如果 Windows 弹出摄像头权限提示，请选择允许。回到主界面后，确认画面中能完整、清楚地看到患者的双眼。

### 4. 完成一次测试呼叫

使用默认眨眼序列进行测试：

**睁眼 1.5 秒 → 闭眼 1 秒 → 睁眼 1 秒 → 闭眼 1.5 秒**

顶部进度条会显示当前动作的完成情况。完成整个序列后，软件会播放呼叫铃声并显示提醒界面。确认声音正常后，可以点击“停止”结束提醒。

正式使用前，请让患者和照护者共同完成至少一次测试，确认摄像头识别和提醒声音都能正常工作。

> 想查看每一步的截图和动画？请打开[完整的首次使用指南](https://JouleEmbodiedAILab.github.io/blink-call/first-use/)。

## 日常怎么使用

完成第一次配置后，每次使用只需要：

1. 双击 `BlinkCall.exe` 打开软件。
2. 确认摄像头画面正常，患者的双眼没有被头发、被子、手或眼镜边框遮挡。
3. 按照当前设置的睁眼、闭眼序列触发呼叫。
4. 如果需要提前结束铃声，照护者可以点击提醒界面上的“停止”。

详细说明请查看[日常使用指南](https://JouleEmbodiedAILab.github.io/blink-call/daily-use/)。

## 常见问题

### 看不到摄像头画面

- 检查 Windows 是否允许软件访问摄像头。
- 检查摄像头是否已经连接，或是否正被其他软件占用。
- 如果电脑有多个摄像头，请在“设置 → 摄像头”中从编号 `0` 开始尝试。

更多说明请查看[摄像头设置](https://JouleEmbodiedAILab.github.io/blink-call/camera/)。

### 完成动作后没有触发呼叫

- 确认双眼完整、清楚地出现在画面中，并尽量保持光线稳定。
- 每个阶段都需要保持睁眼或闭眼，直到对应的进度完成。
- 完成一个阶段后，请在 3 秒内开始下一个阶段，否则进度会重新开始。
- 建议先使用默认动作测试，确认成功后再调整动作和持续时间。

更多说明请查看[眨眼动作设置](https://JouleEmbodiedAILab.github.io/blink-call/blink-pattern/)。

### 听不到提醒声音

- 检查电脑或蓝牙音箱是否静音，音量是否合适。
- 在“设置 → 眨眼呼叫”中确认已经开启呼叫音频。
- 检查软件中选择的铃声、音量和播放时长。

更多说明请查看[提醒声音设置](https://JouleEmbodiedAILab.github.io/blink-call/audio-alert/)。

## 更多帮助

- [完整用户手册](https://JouleEmbodiedAILab.github.io/blink-call/)
- [提交问题](https://github.com/JouleEmbodiedAILab/blink-call/issues)

## 开发者指南

以下内容面向希望从源码运行、修改或打包软件的开发者。普通用户无需执行这些命令。

<details>
<summary><strong>从源码安装并启动</strong></summary>

### 1. 克隆仓库

```bash
git clone https://github.com/JouleEmbodiedAILab/blink-call.git
cd blink-call
```

### 2. 安装 Python 依赖环境

Linux 和 macOS：

```bash
# 默认 Conda 环境名为 blink_call
bash ./scripts/linux/setup_conda.sh [--name <env_name>]
```

Windows：

```powershell
# 默认 Conda 环境名为 blink_call
# 请确保终端可以使用 conda 命令，也可以在 Anaconda Prompt 中运行
powershell -ExecutionPolicy Bypass -File ./scripts/windows/setup_conda.ps1 [-Name <env_name>]
```

### 3. 启动软件

```bash
conda activate blink_call
python -m blink_call.setup_app
```

</details>

<details>
<summary><strong>更换模型文件</strong></summary>

本仓库不负责模型训练与 ONNX 模型文件替换。相关模型的离线训练资源可在以下仓库中获取：

- 人脸检测：[YOLOv6](https://github.com/meituan/YOLOv6)
- 2D 人脸 98 关键点检测：[HRNet](https://github.com/xxlin123/HRNet)
- 眼睛状态分类：[ViTA](https://github.com/Ole7755/ViTA)

获取对应 ONNX 模型文件后，请替换 ModelScope [模型库](https://www.modelscope.cn/models/BlinkCall/blink_call_model_files/files)中的文件。

> [!WARNING]
> 更新 ONNX 模型时，请确保文件路径和文件名保持完全一致。发布软件版本时，请在 ModelScope 仓库中增加一个同版本号的标签。

</details>

<details>
<summary><strong>使用 Nuitka 打包 Windows 版本</strong></summary>

```powershell
conda activate blink_call
powershell -ExecutionPolicy Bypass -File ./scripts/windows/build_nuitka.ps1
```

</details>

<details>
<summary><strong>更新在线用户手册</strong></summary>

请在 `user_manual/` 目录中编辑 `mkdocs.yml` 和对应的 `docs/*.md` 文件。

本地预览：

```bash
mkdocs serve
```

打开 `http://127.0.0.1:8000/` 查看效果。准备发布时执行：

```bash
mkdocs gh-deploy
```

所有 `mkdocs` 命令都应在 `user_manual/` 目录中执行。

</details>

## 许可证

本项目采用 MIT License，详见 [LICENSE](LICENSE)。
