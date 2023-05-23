import typing

import mobase
from PyQt5.QtWidgets import QMessageBox


class MyPlugin(mobase.IPlugin):
    def init(self, organizer: mobase.IOrganizer) -> bool:
        self.__organizer = organizer
        self.__organizer.modList().onModInstalled(self.__onModInstalled)
        return True

    def author(self) -> str:
        return "Ryan McKenzie"

    def description(self) -> str:
        return "Implements (correct) bsa archive extraction"

    def name(self) -> str:
        return "BSA Extractor"

    def settings(self) -> typing.List[mobase.PluginSetting]:
        return []

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(1, 0, 0)

    def __onModInstalled(self, mod: mobase.IModInterface) -> None:
        QMessageBox.information(None, "sample title", "sample text")


def createPlugin() -> mobase.IPlugin:
    return MyPlugin()
