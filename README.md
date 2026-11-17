<div align="center">
  <img width="100" height="100" src="assets/icons/eye.png" alt="Blink Call icon"/>
  <h1><strong>Blink Call</strong></h1>
  <h3><em>A blink-based calling system for ALS patients, detecting custom blink patterns to trigger hands-free calls.</em></h3>
  <p><strong>English</strong> | <a href="README_zh-CN.md">简体中文</a></p>
</div>

<p align="center">
<img src="https://img.shields.io/badge/Python-3.10%2B-blue">
<img src="https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20macOS-orange">
<img src="https://img.shields.io/badge/Type-GUI-green">
<img src="https://img.shields.io/badge/Status-Active-success">
<img src="https://img.shields.io/badge/License-MIT-success">
</p>

> [!WARNING]
> **Disclaimer:** This tool is intended only to support caregiving and cannot replace human supervision. Do not reduce or omit necessary human supervision because you use this tool.

## 📘 Overview
**Blink-Call** is an assistive calling system designed for ALS patients. It recognizes user-defined blink patterns from camera input and triggers visible and audio call alerts without requiring speech, hand movement, or physical touch.

### Key Features
- **Minimal interaction**: Only eye blinks are required.
- **Lightweight resource usage**: Runs in a CPU-only environment with less than 500 MB of memory usage.
- **User-friendly features**:
  - Customizable blink patterns, alert audio, volume, and duration.
  - Support for both local and remote camera modes for flexible deployment.
  - One-click model download and update support.
- **Logging and debugging options** for clinical use and algorithm improvement.

---

## ✨ For User
If you want to get started quickly, begin here:

- 📦 You can download **the latest version of the software** from:
  - [GitHub Latest Release](https://github.com/JouleEmbodiedAILab/blink-call/releases/latest)
  - [Baidu Netdisk](https://pan.baidu.com/s/1Og8-TmnR_yIdsOA2_MHyiw?pwd=fk35)
  - [Quark Netdisk](https://pan.quark.cn/s/e96254bb1153)
- 📖 **User Guide**: [Online User Manual](https://JouleEmbodiedAILab.github.io/blink-call/)

> [!NOTE]
> Currently, the software is only available for direct download and use on Windows.

---

## 🔧 For Developer
This project includes developer documentation and setup guidance to help you get started quickly.

### 🚀 Quick Setup & Launch
- Step 1: Clone the Repository
  ```bash
  git clone https://github.com/JouleEmbodiedAILab/blink-call.git
  cd blink-call
  ```
- Step 2: Setup Conda Environment and Dependencies

  For Linux and macOS
  ```bash
  # default conda environment name -> blink_call
  bash ./scripts/linux/setup_conda.sh [--name <env_name>]
  ```

  For Windows
  ```powershell
  # Default conda environment name: blink_call
  # Ensure that the `conda` command is available in your terminal,
  # or run this in Anaconda Prompt.
  powershell -ExecutionPolicy Bypass -File ./scripts/windows/setup_conda.ps1 [-Name <env_name>]
  ```
- Step 3: Start the Application
  ```bash
  conda activate blink_call
  python -m blink_call.setup_app
  ```

### 🧭 Changing Model Files

This repository does not handle model training and ONNX model file replacement. Offline training resources for the related models can be found in the following repositories:

- Face Detection: [YOLOv6](https://github.com/xxlin123/YOLOv6)
- 2D Face 98 Keypoint Detection: [HRNet](https://github.com/xxlin123/HRNet)
- Eye State Classification: [ViTA](https://github.com/Ole7755/ViTA)

After obtaining the corresponding ONNX model files, replace the files in the ModelScope model [repository](https://www.modelscope.cn/models/BlinkCall/blink_call_model_files/files).

> [!WARNING]
> When updating ONNX models, ensure that both file paths and filenames remain exactly the same.  
> When releasing a software version, please add a tag with the same version name to the ModelScope repository.

### 📦 Building with Nuitka
After development is completed, the software can be built with Nuitka for standalone distribution. The Nuitka build command is shown below.
- For Windows
  ```powershell
  conda activate blink_call
  powershell -ExecutionPolicy Bypass -File ./scripts/windows/build_nuitka.ps1
  ```

### 📚 Docs Update

To update the [online user manual](https://JouleEmbodiedAILab.github.io/blink-call/):

Please edit the contents of `mkdocs.yml` and the corresponding `docs/*.md` files in the `user_manual/` directory.

To preview the documentation locally, run:

```bash
mkdocs serve
```

Then open `http://127.0.0.1:8000/` to view changes in real time.

When you're ready to publish updates, run:

```bash
mkdocs gh-deploy
```

This command will automatically build the site and deploy it to GitHub Pages.

> [!NOTE]
> Note: All `mkdocs` commands should be executed inside the `user_manual` directory.

---

## 📝 License
MIT License. See [LICENSE](LICENSE) for details.
