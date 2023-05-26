import ctypes
import dataclasses
import enum
import logging
import pathlib
import typing

import mobase
from PyQt5.QtCore import QPoint, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTreeWidget,
    qApp,
)


class ProxyPlugin:
    def __init__(self, base_path: str) -> None:
        self.__proxy = ctypes.cdll.LoadLibrary(f"{base_path}/proxy.dll")

        extract_archive = self.__proxy.extract_archive
        extract_archive.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        extract_archive.restype = ctypes.c_int

        get_last_error = self.__proxy.get_last_error
        get_last_error.argtypes = [ctypes.c_char_p, ctypes.c_uint]
        get_last_error.restype = ctypes.c_uint

    def extract_archive(self, archive: str, destination: str) -> bool:
        return self.__proxy.extract_archive(archive.encode(), destination.encode()) == 0

    def get_last_error(self) -> str:
        length = self.__proxy.get_last_error(None, 0)
        buffer = ctypes.create_string_buffer(length)
        self.__proxy.get_last_error(buffer, length)
        return buffer.raw.decode("ascii")


class Format(enum.Enum):
    BSA = "bsa"
    BA2 = "ba2"


@dataclasses.dataclass
class Archive:
    path: pathlib.Path
    extraction_errors = False


@dataclasses.dataclass
class Setting:
    key: str
    description: str
    default_value: mobase.MoVariant


SETTINGS = {
    x.key: x
    for x in [
        Setting(
            "enable_install_dialogue",
            "Enables the popup dialogue to unpack archives when installing them",
            True,
        ),
        Setting(
            "enable_archive_tab_context",
            "Enables the context menu to unpack archives in the archives tab",
            True,
        ),
    ]
}


class MyPlugin(mobase.IPlugin):
    def init(self, organizer: mobase.IOrganizer) -> bool:
        self.__logger: logging.Logger = mobase.logger  # type: ignore

        self.__organizer = organizer
        self.__organizer.modList().onModInstalled(self.__onModInstalled)
        self.__organizer.onUserInterfaceInitialized(self.__onUserInterfaceInitialized)

        self.__proxy = ProxyPlugin(self.__pluginPath())

        self.__organizer.onPluginSettingChanged(self.__onPluginSettingChanged)
        self.__settings: typing.Dict[str, mobase.MoVariant] = {}
        for setting in SETTINGS.values():
            value = self.__organizer.pluginSetting(self.name(), str(setting.key))
            self.__settings[setting.key] = (
                value if value is not None else setting.default_value
            )

        return True

    def author(self) -> str:
        return "Ryan McKenzie"

    def description(self) -> str:
        return "Implements (correct) bsa archive extraction"

    def name(self) -> str:
        return "BSA Extractor 2"

    def settings(self) -> typing.List[mobase.PluginSetting]:
        return [
            mobase.PluginSetting(x.key, x.description, x.default_value)
            for x in SETTINGS.values()
        ]

    def version(self) -> mobase.VersionInfo:
        with open(f"{self.__pluginPath()}/version.txt") as f:
            return mobase.VersionInfo(f.read().strip(), mobase.VersionScheme.REGULAR)

    def __onPluginSettingChanged(
        self,
        plugin_name: str,
        key: str,
        old_value: mobase.MoVariant,
        new_value: mobase.MoVariant,
    ) -> None:
        if plugin_name == self.name() and key in self.__settings:
            self.__settings[key] = (
                new_value if new_value is not None else SETTINGS[key].default_value
            )

    def __onUserInterfaceInitialized(self, window: QMainWindow) -> None:
        self.__window = window

        # disable old bsa extractor plugin
        self.__organizer.setPersistent("BSA Extractor", "enabled", False)

        self.__archive_tree: QTreeWidget = self.__window.findChild(QTreeWidget, "bsaList")  # type: ignore
        signal: pyqtSignal = self.__archive_tree.customContextMenuRequested
        signal.disconnect()  # disable old archive extraction dialogue
        signal.connect(self.__onCustomContextMenuRequested)

    def __onCustomContextMenuRequested(self, pos: QPoint) -> None:
        if not self.__settings["enable_archive_tab_context"]:
            return

        def do_extraction() -> None:
            item = self.__archive_tree.itemAt(pos)
            destination = QFileDialog.getExistingDirectory(self.__window, "Extract BSA")
            if len(destination) == 0:
                return

            if next(pathlib.Path(destination).iterdir(), None) is not None:
                choice = QMessageBox.question(
                    None,
                    "Extract Archives",
                    (
                        "The directory you have selected is not empty.\n"
                        "Are you sure you wish to continue?"
                    ),
                    defaultButton=QMessageBox.No,
                )
                if choice != QMessageBox.Yes:
                    return

            if item.parent() is None:  # separator
                mod_name = item.text(0)
                archives = [item.child(i).text(0) for i in range(item.childCount())]
            else:  # archive
                mod_name = item.parent().text(0)
                archives = [item.text(0)]

            root_path = (
                mod.absolutePath()
                if (mod := self.__organizer.modList().getMod(mod_name)) is not None
                else self.__organizer.managedGame().dataDirectory().absolutePath()
            )

            for archive in archives:
                self.__logger.info(f"Extracting {archive}...")

                if not self.__proxy.extract_archive(
                    f"{root_path}/{archive}", destination
                ):
                    self.__logger.error(f"{archive}: {self.__proxy.get_last_error()}")

        menu = QMenu()
        menu.addAction("Extract...").triggered.connect(do_extraction)
        menu.exec(self.__archive_tree.mapToGlobal(pos))

    def __pluginPath(self) -> str:
        return f"{qApp.applicationDirPath()}/plugins/bsa_extractor"

    def __onModInstalled(self, mod: mobase.IModInterface) -> None:
        if not self.__settings["enable_install_dialogue"]:
            return

        archive_format = self.__archiveFormat()
        if mod.isForeign() or (archive_format is None):
            return

        mod_path = mod.absolutePath()
        archives = [
            Archive(x)
            for x in pathlib.Path(mod_path).glob(f"**/*.{archive_format.value}")
        ]

        if len(archives) > 0:
            do_extract = QMessageBox.question(
                None,
                "Extract Archives",
                (
                    "This mod contains one or more archives.\n"
                    "Would you like to extract them?"
                ),
                defaultButton=QMessageBox.No,
            )

            if do_extract == QMessageBox.Yes:
                destination = mod.absolutePath()
                for archive in archives:
                    self.__logger.info(
                        f"Extracting {archive.path.relative_to(mod_path)}..."
                    )

                    if not self.__proxy.extract_archive(str(archive.path), destination):
                        archive.extraction_errors = True
                        self.__logger.error(
                            f"{archive.path.relative_to(mod_path)}: {self.__proxy.get_last_error()}"
                        )

                if any(map(lambda x: not x.extraction_errors, archives)):
                    do_remove = QMessageBox.question(
                        None,
                        "Remove Archives",
                        "Now that extraction is complete, would you like to remove the old archives?",
                        defaultButton=QMessageBox.Yes,
                    )

                    if do_remove == QMessageBox.Yes:
                        for archive in archives:
                            if not archive.extraction_errors:
                                archive.path.unlink()

    def __archiveFormat(self) -> typing.Optional[Format]:
        game_name = self.__organizer.managedGame().gameName()
        formats = {
            "Morrowind": Format.BSA,
            "Oblivion": Format.BSA,
            "Fallout 3": Format.BSA,
            "New Vegas": Format.BSA,
            "Skyrim": Format.BSA,
            "Fallout 4": Format.BA2,
            "Skyrim Special Edition": Format.BSA,
            "Skyrim VR": Format.BSA,
            "Fallout 4 VR": Format.BA2,
            "Enderal": Format.BSA,
            "TTW": Format.BSA,
        }

        return formats.get(game_name)


def createPlugin() -> mobase.IPlugin:
    return MyPlugin()
