"""
VoiceForge — Offline Text-to-Speech Desktop Application
"""

from setuptools import find_packages, setup

setup(
    name="voiceforge",
    version="1.0.0",
    description="Professional offline TTS desktop application",
    packages=find_packages(include=["app", "app.*"]),
    include_package_data=True,
    python_requires=">=3.11,<3.14",
    install_requires=[
        "PySide6>=6.6.0,<7",
        "numpy>=1.26.0,<3",
        "soundfile>=0.12.1",
        "onnxruntime>=1.17.0",
        "kokoro-onnx>=0.4.0",
        "python-docx>=1.1.0",
        "pypdf>=4.0.0",
        "beautifulsoup4>=4.12.0",
        "psutil>=5.9.0",
    ],
    extras_require={
        "piper": ["piper-tts>=1.2.0"],
        "dev": ["pytest>=8.0.0", "pyinstaller>=6.0.0"],
    },
    entry_points={
        "console_scripts": [
            "voiceforge=app.cli:main",
            "voiceforge-gui=main:run_gui",
        ],
    },
)
