import atexit
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
import winreg
import zipfile
from functools import cache
from pathlib import Path
from threading import Thread
from typing import Iterator

import pystray
import pyuac
from PIL import Image
from pystray import MenuItem

from IIcon import IIcon


def get_resource_path(resource: str) -> str:
    # if sys.executable.endswith("NeteaseModUpdater.exe"):
    #     return str(Path(sys.argv[0]).parent.parent.joinpath("resource").joinpath(resource))
    # else:
    return str(Path(sys.argv[0]).parent.joinpath("resource").joinpath(resource))


def notify(title: str, message: str, timeout: int = 10) -> None:
    icon.notify(message, title)

    def timeout_remove() -> None:
        time.sleep(timeout)
        icon.remove_notification()

    Thread(target=timeout_remove, daemon=True).start()


class DirWalker:
    def __init__(self, path: str):
        self.dirs: list[str] = []
        self.files: list[str] = []
        self.walk(path)

    def walk(self, dir_path: str) -> None:
        for i in os.listdir(dir_path):
            path = dir_path + "\\" + i
            if os.path.isfile(path):
                self.files.append(path)
            elif os.path.isdir(path):
                self.dirs.append(path)

    def __iter__(self) -> Iterator[str]:
        return self

    def __next__(self) -> str:
        if self.files:
            return self.files.pop(0)
        else:
            if self.dirs:
                self.walk(self.dirs.pop(0))
                return self.__next__()
            else:
                raise StopIteration


@cache
def get_mod_id(jar: str) -> str | None:
    try:
        with zipfile.ZipFile(jar, "r") as zip_file:
            zip_file.extract("META-INF/mods.toml", get_resource_path("temp/"))
            mod_info = tomllib.loads(open(get_resource_path("temp/META-INF/mods.toml"), "r", encoding="utf-8").read())
            return mod_info["mods"][0]["modId"]
    except OSError:
        return None
    except TypeError:
        return None
    except KeyError:
        return None
    except UnicodeDecodeError:
        return None
    except Exception as err:

        notify("网易模组替换器", f"获取modid({os.path.basename(jar)})时出现异常:{err}", timeout=1)
        return None


class Updater:
    VERSION_MAP: dict[str, str] = {
        "1.16.4": "16",
        "1.18.1": "18",
        "1.20.1": "20",
        "1.20.6": "20_6",
        "1.21": "21",
    }

    def __init__(self) -> None:
        self.game_path: str | None = None
        self.has_path: bool = True
        self.toggle: bool = True
        self.auto_skip: bool = True
        self.complete_delete: bool = False
        self.should_exit: bool = False
        self.configs: list[str] = ["toggle", "auto_skip", "complete_delete"]

        atexit.register(self.save_config)

        self.load_config()
        self.init()

        self.update_init = False

    def save_config(self) -> None:
        with open(get_resource_path("config.json"), "w") as config_file:
            configs = {}
            for config in self.configs:
                value = getattr(self, config)
                configs[config] = value
            config_file.write(json.dumps(configs, indent=True))

    def load_config(self) -> None:
        if os.path.exists(get_resource_path("config.json")):
            with open(get_resource_path("config.json"), "r", encoding="utf-8") as config_file:
                configs = json.loads(config_file.read())
                for config in self.configs:
                    value = configs.get(config)
                    if value is not None:
                        setattr(self, config, value)

    def init(self) -> None:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, fr"SOFTWARE\Netease\MCLauncher")
            with key:
                value, _ = winreg.QueryValueEx(key, "DownloadPath")
                self.game_path = value
        except OSError:
            self.has_path = False
            self.toggle = False
            notify("网易模组替换器", "无法找到安装路径(可能游戏未安装)", timeout=10)
            return

        for mcversion, mark_version in self.VERSION_MAP.items():
            cache_mods_path = Path(self.game_path).joinpath(
                "cache", "game", f"V_{mcversion.replace('.', '_')}", "mods"
            )
            os.makedirs(cache_mods_path, exist_ok=True)
            shutil.copy(get_resource_path(f"mark/1@{mark_version}"), str(cache_mods_path))

    def update(self) -> None:
        if not self.update_init:
            notify("网易模组替换器", f"网易模组替换器 已启动，修改配置请查看系统托盘")
            if len(sys.argv) > 1 and sys.argv[-1] == "set_startup":
                set_startup()
            if len(sys.argv) > 1 and sys.argv[-1] == "remove_startup":
                remove_startup()
            self.update_init = True
        if self.should_exit:
            sys.exit(0)
        if self.toggle:
            for mcversion, version in self.VERSION_MAP.items():
                if os.path.exists(rf"{self.game_path}\Game\.minecraft\mods\1@{version}"):
                    mods_id = [get_mod_id(i) for i in DirWalker(rf"{self.game_path}\Game\.minecraft\mods")
                               if os.path.splitext(i)[1] == ".jar"]
                    self.replace(mcversion, version, mods_id)
                    notify("网易模组替换器", f"检测到游戏{mcversion}启动，已替换全部文件", timeout=10)

    def replace(self, mcversion: str, version: str, mods_id: list[str | None]) -> None:
        if self.complete_delete:
            for i in DirWalker(f"{self.game_path}\\Game\\.minecraft\\mods"):
                os.remove(i)
            mods_id = []
        try:
            for i in DirWalker(get_resource_path(f"{mcversion}")):
                if self.auto_skip and os.path.splitext(i)[1] == ".jar":
                    if get_mod_id(i) in mods_id:
                        continue
                os.makedirs(f"{self.game_path}\\Game\\.minecraft\\{str(Path(i).parent.name)}", exist_ok=True)
                shutil.copy(i, f"{self.game_path}\\Game\\.minecraft\\{str(Path(i).parent.name)}")
            os.remove(rf"{self.game_path}\Game\.minecraft\mods\1@{version}")
        except OSError:
            pass

    def on_clicked_complete_delete(self) -> None:
        self.complete_delete = not self.complete_delete

    def on_clicked_toggled(self) -> None:
        self.toggle = not self.toggle

    def on_clicked_auto_skip(self) -> None:
        self.auto_skip = not self.auto_skip

    def on_exit(self) -> None:
        self.should_exit = True

def open_version_folder(ic: IIcon, mi: MenuItem):
    try_mkdir(os.path.realpath(get_resource_path(mi.text)))
    subprocess.run(f'explorer /root,"{os.path.realpath(get_resource_path(mi.text))}"', shell=True)


def try_mkdir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def has_startup() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0)
        with key:
            value, _ = winreg.QueryValueEx(key, "NeteaseModUpdater")
            if value == str(Path(__file__).parent.parent.joinpath("NeteaseModUpdater.exe")):
                return True
    except OSError:
        return False


def set_startup() -> None:
    global startup
    try:
        if not pyuac.isUserAdmin():
            sys.argv.append("set_startup")
            pyuac.runAsAdmin(wait=False)
            os._exit(0)
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                             winreg.KEY_ALL_ACCESS)
        with key:
            winreg.SetValueEx(key, "NeteaseModUpdater", 0, winreg.REG_SZ,
                              str(Path(__file__).parent.parent.joinpath("NeteaseModUpdater.exe")))
            notify("网易模组替换器", "已成功设置开机自启动")
            startup = True
    except OSError as err:
        notify("网易模组替换器", f"开机自启动失败: {err.__class__.__name__}")


def remove_startup() -> None:
    global startup
    try:
        if not pyuac.isUserAdmin():
            sys.argv.append("remove_startup")
            pyuac.runAsAdmin(wait=False)
            os._exit(0)
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                             winreg.KEY_SET_VALUE, winreg.KEY_ALL_ACCESS | winreg.KEY_WRITE | winreg.KEY_CREATE_SUB_KEY)
        with key:
            winreg.DeleteValue(key, "NeteaseModUpdater")
            notify("网易模组替换器", "已成功取消开机自启动")
            startup = False
    except OSError as err:
        notify("网易模组替换器", f"开机自启动关闭失败: {err.__class__.__name__}")


def change_startup() -> None:
    global startup
    if startup:
        remove_startup()
    else:
        set_startup()


if __name__ == '__main__':
    sys.path.append(str(Path(__file__).parent.parent))
    startup = has_startup()

    if len(sys.argv) > 1 and sys.argv[-1] == "set_startup":
        startup = True
    if len(sys.argv) > 1 and sys.argv[-1] == "remove_startup":
        startup = False

    update = Updater()
    menu = pystray.Menu(
        pystray.MenuItem('开启', update.on_clicked_toggled, checked=lambda item: update.toggle),
        pystray.MenuItem('自动跳过相同id模组', update.on_clicked_auto_skip, checked=lambda item: update.auto_skip),
        pystray.MenuItem('删除全部原模组', update.on_clicked_complete_delete,
                         checked=lambda item: update.complete_delete),
        pystray.MenuItem('开机自启动', change_startup, checked=lambda item: startup),
        pystray.MenuItem("打开模组源文件夹",
                         pystray.Menu(pystray.MenuItem("1.16.4", open_version_folder),
                                      pystray.MenuItem("1.18.1", open_version_folder),
                                      pystray.MenuItem("1.20.1", open_version_folder),
                                      pystray.MenuItem("1.20.6", open_version_folder),
                                      pystray.MenuItem("1.21", open_version_folder), )
                         ),
        pystray.MenuItem("修复识别文件", update.init),
        pystray.MenuItem('退出', update.on_exit)
    )
    icon = IIcon('NeteaseModUpdater', Image.open(get_resource_path('icon.ico')),
                 '网易模组替换器(.minecraft中的任意文件)',
                 menu, on_update=update.update,
                 on_init=lambda: notify("网易模组替换器", f"网易模组替换器 已启动，修改配置请查看系统托盘"))
    icon.run()
