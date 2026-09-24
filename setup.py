from setuptools import find_packages, setup

setup(
    name="iptv-gen",
    version="0.1.0",
    description="国内 IPTV M3U 生成器：采集 / 检测 / 排序 / 生成",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "iptv-gen=iptv_gen.cli:main",
        ]
    },
)
