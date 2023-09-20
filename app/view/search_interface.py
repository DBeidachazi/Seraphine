import threading
import time

import pyperclip
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QFrame,
                             QSpacerItem, QSizePolicy, QLabel, QStackedWidget, QWidget)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from qfluentwidgets import (SmoothScrollArea, LineEdit, PushButton, ToolButton, InfoBar,
                            InfoBarPosition, ToolTipFilter, ToolTipPosition, Theme, isDarkTheme, FlyoutViewBase, Flyout,
                            CardWidget, IndeterminateProgressRing, FlyoutView, FlyoutAnimationType, ComboBox,
                            StateToolTip)

from ..common.style_sheet import StyleSheet
from ..common.icons import Icon
from ..common.config import cfg
from ..components.champion_icon_widget import RoundIcon
from ..components.mode_filter_widget import ModeFilterWidget
from ..components.summoner_name_button import SummonerName
from ..lol.connector import LolClientConnector, connector
from ..lol.tools import processGameData, processGameDetailData


class GamesTab(QFrame):
    gamesInfoReady = pyqtSignal(int)
    tabClicked = pyqtSignal(str)
    gameDetailReady = pyqtSignal(dict)

    def __init__(self, parnet=None):
        super().__init__(parnet)
        self.setFixedWidth(160)
        self.vBoxLayout = QVBoxLayout(self)

        self.stateTooltip = None

        self.stackWidget = QStackedWidget()
        self.buttonsLayout = QHBoxLayout()

        self.prevButton = ToolButton(Icon.CHEVRONLEFT)
        self.pageLabel = QLabel(" ")
        self.nextButton = ToolButton(Icon.CHEVRONRIGHT)

        self.currentIndex = 0
        self.gamesNumberPerPage = 10
        self.maxPage = None

        self.puuid = None
        self.games = []

        self.begIndex = 0

        self.triggerByButton = True

        self.__initWidget()
        self.__initLayout()
        self.__connectSignalToSlot()

    def __initWidget(self):
        self.pageLabel.setAlignment(Qt.AlignCenter)
        self.prevButton.setVisible(False)
        self.prevButton.setEnabled(False)
        self.nextButton.setVisible(False)
        self.nextButton.setEnabled(False)

    def __initLayout(self):
        defaultWidget = QWidget()
        layout = QVBoxLayout(defaultWidget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.stackWidget.addWidget(defaultWidget)
        self.stackWidget.setCurrentIndex(self.currentIndex)

        self.buttonsLayout.addWidget(self.prevButton)
        self.buttonsLayout.addWidget(self.pageLabel)
        self.buttonsLayout.addWidget(self.nextButton)

        self.vBoxLayout.addWidget(self.stackWidget)
        self.vBoxLayout.addSpacing(10)
        self.vBoxLayout.addLayout(self.buttonsLayout)

    def __connectSignalToSlot(self):
        self.prevButton.clicked.connect(self.__onPrevButtonClicked)
        self.nextButton.clicked.connect(self.__onNextButtonClicked)

        self.gamesInfoReady.connect(self.__onGamesInfoReady)
        self.tabClicked.connect(self.__onTabClicked)
        self.gameDetailReady.connect(self.__onGameDetailReady)

    def __onTabClicked(self, gameId):

        def _():
            self.parent().gameDetailView.showLoadingPage.emit()
            game = connector.getGameDetailByGameId(gameId)
            game = processGameDetailData(self.puuid, game)
            self.gameDetailReady.emit(game)
            self.parent().gameDetailView.hideLoadingPage.emit()

        threading.Thread(target=_).start()

    def __onGameDetailReady(self, game):
        self.parent().gameDetailView.updateGame(game)

    def __onPrevButtonClicked(self):
        self.currentIndex -= 1
        self.stackWidget.setCurrentIndex(self.currentIndex)

        self.nextButton.setEnabled(True)
        self.pageLabel.setText(f"{self.currentIndex}")

        if self.currentIndex == 1:
            self.prevButton.setEnabled(False)

    def questionPage(self, page, queueId=None) -> bool:
        """

        @param page: 需要查询的页码
        @param queueId: 过滤条件
        @return: True -> 此页可以直接返回, False -> 此页未加载完成或超出最大页码
        """
        games = self.window().searchInterface.games

        if queueId is None:
            maxPage = int(len(games) / 10)
        else:
            buffer = self.window().searchInterface.queueIdBuffer.get(queueId, [])
            maxPage = int(len(buffer) / 10)

        return page < maxPage

    # FIXME 信号部分未声明参数
    def __onNextButtonClicked(self, page: int = 1, queueId=None):
        """

        @param page: 目标页
        """

        assert page > 0

        def waitLoadPage():
            while not self.questionPage(page, queueId):
                time.sleep(.5)
            if self.stateTooltip:
                self.stateTooltip.setContent(
                    self.tr('Data loading completed!') + ' 😆')
                self.stateTooltip.setState(True)
                self.stateTooltip = None
            self.nextButton.setEnabled(True)
            self.__onNextButtonClicked(page, queueId)

        games = self.window().searchInterface.games
        loadThread = self.window().searchInterface.loadGamesThread  # 用于判断还有无获取新数据

        if queueId is None:
            maxPage = int(len(games) / 10)
            if page >= maxPage:
                if loadThread.is_alive():
                    self.nextButton.setEnabled(False)
                    if not self.stateTooltip:
                        self.stateTooltip = StateToolTip(
                            self.tr('Data is loading'), self.tr('Please wait patiently'), self.window())
                        self.stateTooltip.move(self.stateTooltip.getSuitablePos())
                        self.stateTooltip.show()
                    threading.Thread(target=waitLoadPage).start()
                    return
                else:  # 已到最后一页
                    data = games[(page - 1) * 10:]
                    self.nextButton.setEnabled(False)
            else:
                data = games[(page - 1) * 10: page * 10]
        else:
            buffer = self.window().searchInterface.queueIdBuffer.get(queueId, [])
            maxPage = int(len(buffer) / 10)
            if page >= maxPage:
                if loadThread.is_alive():
                    self.nextButton.setEnabled(False)
                    if not self.stateTooltip:
                        self.stateTooltip = StateToolTip(
                            self.tr('Data is loading'), self.tr('Please wait patiently'), self.window())
                        self.stateTooltip.move(self.stateTooltip.getSuitablePos())
                        self.stateTooltip.show()
                    threading.Thread(target=waitLoadPage).start()
                    return
                else:
                    tmpBuf = buffer[(page - 1) * 10:]
                    self.nextButton.setEnabled(False)
            else:
                tmpBuf = buffer[(page - 1) * 10: page * 10]

            data = []
            for idx in tmpBuf:
                data.append(games[idx])

        self.updateNextPageTabs(data)
        # self.stackWidget.setCurrentIndex(self.currentIndex)
        # self.pageLabel.setText(f"{self.currentIndex}")
        # if self.currentIndex == self.maxPage:
        #     self.nextButton.setEnabled(False)
        self.prevButton.setEnabled(True)
        self.currentIndex = page

        # if len(self.stackWidget) <= self.currentIndex:
        #     self.nextButton.setEnabled(False)
        #     self.prevButton.setEnabled(False)
        #     self.updateGames(self.currentIndex)
        # else:
        #     self.stackWidget.setCurrentIndex(self.currentIndex)
        #     self.pageLabel.setText(f"{self.currentIndex}")
        #     if self.currentIndex == self.maxPage:
        #         self.nextButton.setEnabled(False)
        #     self.prevButton.setEnabled(True)

    def backToDefaultPage(self):
        self.currentIndex = 0
        self.maxPage = None
        self.games = []
        self.puuid = None

        for i in reversed(range(len(self.stackWidget))):
            if i != 0:
                widget = self.stackWidget.widget(i)
                self.stackWidget.removeWidget(widget)
                widget.deleteLater()

        self.stackWidget.setCurrentIndex(0)
        self.pageLabel.setText(" ")

        self.prevButton.setEnabled(False)
        self.nextButton.setEnabled(False)
        self.prevButton.setVisible(False)
        self.nextButton.setVisible(False)

    def firstCall(self, puuid):
        if self.puuid != None:
            self.backToDefaultPage()

        self.puuid = puuid
        self.first = True
        self.prevButton.setVisible(True)
        self.nextButton.setVisible(True)
        self.__onNextButtonClicked()
        # self.currentIndex += 1
        # self.stackWidget.setCurrentIndex(self.currentIndex)
        # self.pageLabel.setText(f"{self.currentIndex}")
        # if self.currentIndex == self.maxPage:
        #     self.nextButton.setEnabled(False)
        # if len(self.games) == 0:
        #     self.__showEmptyPage()

    def updatePuuid(self, puuid):
        if self.puuid != None:
            self.backToDefaultPage()

        self.puuid = puuid
        self.first = True
        self.prevButton.setVisible(True)
        self.nextButton.setVisible(True)
        self.__onNextButtonClicked()

    def updateNextPageTabs(self, data):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        for game in data:
            tab = GameTab(game)
            layout.addWidget(tab)

        if len(data) < self.gamesNumberPerPage:
            layout.addSpacerItem(QSpacerItem(
                1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))

        self.stackWidget.addWidget(widget)
        self.stackWidget.setCurrentIndex(self.currentIndex)
        self.pageLabel.setText(f"{self.currentIndex}")

        # if self.currentIndex != self.maxPage:
        #     self.nextButton.setEnabled(True)
        #
        # if self.currentIndex != 1:
        #     self.prevButton.setEnabled(True)

        if self.first and self.triggerByButton:
            gameId = layout.itemAt(0).widget().gameId
            self.tabClicked.emit(str(gameId))
            self.first = False

        mainWindow = self.window()
        mainWindow.checkAndSwitchTo(mainWindow.searchInterface)

    def updateTabs(self, begin, n):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        for i in range(begin, begin + n):
            tab = GameTab(self.games[i])
            layout.addWidget(tab)

        if n < self.gamesNumberPerPage:
            layout.addSpacerItem(QSpacerItem(
                1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))

        self.stackWidget.addWidget(widget)
        self.stackWidget.setCurrentIndex(self.currentIndex)
        self.pageLabel.setText(f"{self.currentIndex}")

        if self.currentIndex != self.maxPage:
            self.nextButton.setEnabled(True)

        if self.currentIndex != 1:
            self.prevButton.setEnabled(True)

        if self.first and self.triggerByButton:
            gameId = layout.itemAt(0).widget().gameId
            self.tabClicked.emit(str(gameId))
            self.first = False

        mainWindow = self.window()
        mainWindow.checkAndSwitchTo(mainWindow.searchInterface)

    def updateGames(self, page):
        def _(page, callback=None):
            tmp_games_cnt = len(self.games)
            endIndex = self.begIndex + 9
            while True:
                games = connector.getSummonerGamesByPuuid(
                    self.puuid, self.begIndex, endIndex)

                for game in games["games"]:
                    if time.time() - game['gameCreation'] / 1000 > 60 * 60 * 24 * 365:
                        self.maxPage = page
                        break

                    if self.games:
                        # 避免重复添加
                        if game['gameCreation'] >= self.games[-1]["timeStamp"]:
                            continue

                    if game["queueId"] in self.window().searchInterface.filterData:
                        self.games += [processGameData(game)]

                if len(self.games) - tmp_games_cnt >= 10:
                    self.maxPage = page + 1
                    self.games = self.games[:10 * self.maxPage]
                    break

                self.begIndex = endIndex + 1
                endIndex += 10
            if callback:
                callback()

        if page == 1:  # 第一页时加载自身数据, 完成后切换; 并且并发加载下一页数据
            def firstPageCallback():
                """
                禁用下一页按钮必须在gamesInfoReady信号之后, 所以要另外拿出来做回调
                """
                self.gamesInfoReady.emit(page)
                self.nextButton.setEnabled(False)
                threading.Thread(target=_, args=(page + 1, lambda: self.nextButton.setEnabled(True))).start()

            threading.Thread(target=_, args=(page, firstPageCallback)).start()
        else:  # 除第一页外, 直接切换到该页, 并加载下一页;
            self.gamesInfoReady.emit(page)
            self.nextButton.setEnabled(False)
            threading.Thread(target=_, args=(page + 1, lambda: self.nextButton.setEnabled(True))).start()

    def __onGamesInfoReady(self, page):
        if len(self.games) == 0:
            self.__showEmptyPage()
            return

        m = self.gamesNumberPerPage
        begin = m * (page - 1)

        n = 10 if self.currentIndex != self.maxPage else min(
            m, (len(self.games) - 1) % m + 1)

        self.updateTabs(begin, n)

    def __showEmptyPage(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(self.tr("Empty"))
        label.setObjectName("emptyLabel")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        self.stackWidget.addWidget(widget)
        self.stackWidget.setCurrentIndex(self.currentIndex)
        self.pageLabel.setText(f"{self.currentIndex}")
        self.prevButton.setVisible(False)
        self.nextButton.setVisible(False)
        self.pageLabel.setText(" ")


class GameDetailView(QFrame):
    summonerNameClicked = pyqtSignal(str)

    showLoadingPage = pyqtSignal()
    hideLoadingPage = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vBoxLayout = QVBoxLayout(self)
        self.titleBar = GameTitleBar()

        self.teamView1 = TeamView()
        self.teamView2 = TeamView()

        self.extraTeamView1 = TeamView()
        self.extraTeamView2 = TeamView()

        self.processRing = IndeterminateProgressRing()

        self.__initLayout()
        self.__connectSignalToSlot()

    def __connectSignalToSlot(self):
        self.showLoadingPage.connect(
            lambda: self.__setLoadingPageEnabeld(True))
        self.hideLoadingPage.connect(
            lambda: self.__setLoadingPageEnabeld(False))

    def clear(self):
        for i in reversed(range(self.vBoxLayout.count())):
            item = self.vBoxLayout.itemAt(i)
            self.vBoxLayout.removeItem(item)

            if item.widget():
                item.widget().deleteLater()

        self.titleBar = GameTitleBar()

        self.teamView1 = TeamView()
        self.teamView2 = TeamView()

        self.extraTeamView1 = TeamView()
        self.extraTeamView2 = TeamView()

        self.processRing = IndeterminateProgressRing()

        self.__initLayout()

    def __initLayout(self):
        self.vBoxLayout.addWidget(self.titleBar)
        self.vBoxLayout.addWidget(self.teamView1)
        self.vBoxLayout.addWidget(self.teamView2)

        self.vBoxLayout.addWidget(self.extraTeamView1)
        self.vBoxLayout.addWidget(self.extraTeamView2)

        self.vBoxLayout.addWidget(self.processRing, alignment=Qt.AlignCenter)

        self.processRing.setVisible(False)
        self.extraTeamView1.setVisible(False)
        self.extraTeamView2.setVisible(False)

        # self.vBoxLayout.addSpacerItem(
        #     QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def updateGame(self, game: dict):
        isCherry = game["queueId"] == 1700
        mapIcon = QPixmap(game["mapIcon"]).scaled(
            54, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if game["remake"]:
            result = self.tr("Remake")
            color = "162, 162, 162"
        elif game["win"]:
            result = self.tr("Win")
            color = "57, 176, 27"
        else:
            result = self.tr("Lose")
            color = "211, 25, 12"

        if isCherry:
            cherryResult = game["cherryResult"]
            if cherryResult == 1:
                result = self.tr("1st")
            elif cherryResult == 2:
                result = self.tr("2nd")
            elif cherryResult == 3:
                result = self.tr("3rd")
            else:
                result = self.tr("4th")

        self.titleBar.updateTitleBar(
            mapIcon, result, game["mapName"], game["modeName"], game["gameDuration"], game["gameCreation"],
            game["gameId"], color
        )

        team1 = game["teams"][100]
        team2 = game["teams"][200]

        self.teamView1.updateTeam(team1, isCherry, self.tr("1st"))
        self.teamView1.updateSummoners(team1["summoners"])

        self.teamView2.updateTeam(team2, isCherry, self.tr("2nd"))
        self.teamView2.updateSummoners(team2["summoners"])

        self.extraTeamView1.setVisible(isCherry)
        self.extraTeamView2.setVisible(isCherry)

        if isCherry:
            team3 = game["teams"][300]
            team4 = game["teams"][400]

            self.extraTeamView1.updateTeam(team3, isCherry, self.tr("3rd"))
            self.extraTeamView1.updateSummoners(team3["summoners"])

            self.extraTeamView2.updateTeam(team4, isCherry, self.tr("4th"))
            self.extraTeamView2.updateSummoners(team4["summoners"])

    def __setLoadingPageEnabeld(self, enable):
        if not cfg.get(cfg.showTierInGameInfo):
            return

        self.titleBar.setVisible(not enable)
        self.teamView1.setVisible(not enable)
        self.teamView2.setVisible(not enable)

        if enable:
            self.extraTeamView1.setVisible(not enable)
            self.extraTeamView2.setVisible(not enable)

        self.processRing.setVisible(enable)


class TeamView(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.vBoxLayout = QVBoxLayout(self)
        self.titleBarLayout = QHBoxLayout()
        self.summonersLayout = QVBoxLayout()

        self.teamResultLabel = QLabel()
        self.towerIconLabel = QLabel()
        self.towerKillsLabel = QLabel()
        self.inhibitorIconLabel = QLabel()
        self.inhibitorKillsLabel = QLabel()
        self.baronIconLabel = QLabel()
        self.baronKillsLabel = QLabel()
        self.dragonIconLabel = QLabel()
        self.dragonKillsLabel = QLabel()
        self.riftHeraldIconLabel = QLabel()
        self.riftHeraldKillsLabel = QLabel()

        self.bansButton = PushButton("Bans")
        self.csIconLabel = QLabel()
        self.goldIconLabel = QLabel()
        self.dmgIconLabel = QLabel()
        self.kdaLabel = QLabel()

        self.isToolTipInit = False

        self.bansFlyOut = None

        self.__initWidget()
        self.__initLayout()

        cfg.themeChanged.connect(self.__updateIconColor)
        self.bansButton.clicked.connect(lambda: Flyout.make(
            self.bansFlyOut, self.bansButton, self, isDeleteOnClose=False))

    def __initWidget(self):
        self.teamResultLabel.setObjectName("teamResult")

        self.towerIconLabel.setFixedWidth(24)
        self.inhibitorIconLabel.setFixedWidth(24)
        self.baronIconLabel.setFixedWidth(24)
        self.dragonIconLabel.setFixedWidth(24)
        self.riftHeraldIconLabel.setFixedWidth(24)

        self.bansButton.setVisible(False)

        self.kdaLabel.setFixedWidth(100)
        self.kdaLabel.setAlignment(Qt.AlignCenter)
        self.csIconLabel.setFixedWidth(50)
        self.csIconLabel.setAlignment(Qt.AlignCenter)
        self.goldIconLabel.setFixedWidth(60)
        self.goldIconLabel.setAlignment(Qt.AlignCenter)
        self.dmgIconLabel.setFixedWidth(70)
        self.dmgIconLabel.setAlignment(Qt.AlignCenter)

        self.csIconLabel.setVisible(False)
        self.goldIconLabel.setVisible(False)

        self.dmgIconLabel.setObjectName("dmgIconLabel")

    def __initToolTip(self):
        self.towerIconLabel.setToolTip(self.tr("Tower destroyed"))
        self.towerIconLabel.setAlignment(Qt.AlignCenter)
        self.inhibitorIconLabel.setToolTip(self.tr("Inhibitor destroyed"))
        self.inhibitorIconLabel.setAlignment(Qt.AlignCenter)
        self.baronIconLabel.setToolTip(self.tr("Baron Nashor killed"))
        self.baronIconLabel.setAlignment(Qt.AlignCenter)
        self.dragonIconLabel.setToolTip(self.tr("Dragon killed"))
        self.dragonIconLabel.setAlignment(Qt.AlignCenter)
        self.riftHeraldIconLabel.setToolTip(self.tr("Rift Herald killed"))
        self.riftHeraldIconLabel.setAlignment(Qt.AlignCenter)

        self.towerIconLabel.installEventFilter(ToolTipFilter(
            self.towerIconLabel, 500, ToolTipPosition.TOP))
        self.inhibitorIconLabel.installEventFilter(ToolTipFilter(
            self.inhibitorIconLabel, 500, ToolTipPosition.TOP))
        self.baronIconLabel.installEventFilter(ToolTipFilter(
            self.baronIconLabel, 500, ToolTipPosition.TOP))
        self.dragonIconLabel.installEventFilter(ToolTipFilter(
            self.dragonIconLabel, 500, ToolTipPosition.TOP))
        self.riftHeraldIconLabel.installEventFilter(ToolTipFilter(
            self.riftHeraldIconLabel, 500, ToolTipPosition.TOP))

        self.towerKillsLabel.setToolTip(self.tr("Tower destroyed"))
        self.inhibitorKillsLabel.setToolTip(self.tr("Inhibitor destroyed"))
        self.baronKillsLabel.setToolTip(self.tr("Baron Nashor killed"))
        self.dragonKillsLabel.setToolTip(self.tr("Dragon killed"))
        self.riftHeraldKillsLabel.setToolTip(self.tr("Rift Herald killed"))

        self.towerKillsLabel.installEventFilter(ToolTipFilter(
            self.towerKillsLabel, 500, ToolTipPosition.TOP))
        self.inhibitorKillsLabel.installEventFilter(ToolTipFilter(
            self.inhibitorKillsLabel, 500, ToolTipPosition.TOP))
        self.baronKillsLabel.installEventFilter(ToolTipFilter(
            self.baronKillsLabel, 500, ToolTipPosition.TOP))
        self.dragonKillsLabel.installEventFilter(ToolTipFilter(
            self.dragonKillsLabel, 500, ToolTipPosition.TOP))
        self.riftHeraldKillsLabel.installEventFilter(ToolTipFilter(
            self.riftHeraldKillsLabel, 500, ToolTipPosition.TOP))

        self.csIconLabel.setToolTip(self.tr("Minions killed"))
        self.goldIconLabel.setToolTip(self.tr("Gold earned"))
        self.dmgIconLabel.setToolTip(self.tr("Damage dealed to champions"))
        self.csIconLabel.installEventFilter(ToolTipFilter(
            self.csIconLabel, 500, ToolTipPosition.TOP))
        self.goldIconLabel.installEventFilter(ToolTipFilter(
            self.goldIconLabel, 500, ToolTipPosition.TOP))
        self.dmgIconLabel.installEventFilter(ToolTipFilter(
            self.dmgIconLabel, 500, ToolTipPosition.TOP))

    def __initLayout(self):
        self.teamResultLabel.setFixedHeight(43)
        self.teamResultLabel.setFixedWidth(55)

        self.titleBarLayout.setSpacing(0)
        self.titleBarLayout.addWidget(self.teamResultLabel)
        self.titleBarLayout.addSpacing(18)
        self.titleBarLayout.addWidget(self.towerIconLabel)
        self.titleBarLayout.addWidget(self.towerKillsLabel)
        self.titleBarLayout.addSpacing(18)
        self.titleBarLayout.addWidget(self.inhibitorIconLabel)
        self.titleBarLayout.addWidget(self.inhibitorKillsLabel)
        self.titleBarLayout.addSpacing(18)
        self.titleBarLayout.addWidget(self.baronIconLabel)
        self.titleBarLayout.addWidget(self.baronKillsLabel)
        self.titleBarLayout.addSpacing(18)
        self.titleBarLayout.addWidget(self.dragonIconLabel)
        self.titleBarLayout.addWidget(self.dragonKillsLabel)
        self.titleBarLayout.addSpacing(18)
        self.titleBarLayout.addWidget(self.riftHeraldIconLabel)
        self.titleBarLayout.addWidget(self.riftHeraldKillsLabel)
        self.titleBarLayout.addSpacerItem(QSpacerItem(
            1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.titleBarLayout.addWidget(self.bansButton)
        self.titleBarLayout.addSpacing(59)
        self.titleBarLayout.addWidget(self.kdaLabel)
        self.titleBarLayout.addSpacing(6)
        self.titleBarLayout.addWidget(self.csIconLabel)
        self.titleBarLayout.addSpacing(6)
        self.titleBarLayout.addWidget(self.goldIconLabel)
        self.titleBarLayout.addSpacing(6)
        self.titleBarLayout.addWidget(self.dmgIconLabel)
        self.titleBarLayout.addSpacing(7)

        self.summonersLayout.setContentsMargins(0, 0, 0, 0)

        self.vBoxLayout.setContentsMargins(11, 0, 11, 11)
        self.vBoxLayout.addLayout(self.titleBarLayout)
        self.vBoxLayout.addLayout(self.summonersLayout)
        # self.vBoxLayout.addSpacerItem(
        #     QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def updateTeam(self, team, isCherry, result):
        if not self.isToolTipInit:
            self.isToolTipInit = True
            self.__initToolTip()

        win = team['win']
        baronIcon = team['baronIcon']
        baronKills = team['baronKills']
        dragonIcon = team['dragonIcon']
        dragonKills = team['dragonKills']
        riftHeraldIcon = team['riftHeraldIcon']
        riftHeraldKills = team['riftHeraldKills']
        inhibitorIcon = team['inhibitorIcon']
        inhibitorKills = team['inhibitorKills']
        towerIcon = team['towerIcon']
        towerKills = team['towerKills']
        kills = team['kills']
        deaths = team['deaths']
        assists = team['assists']
        bans = team['bans']

        if isCherry:
            self.teamResultLabel.setText(result)
        elif win == "Win":
            self.teamResultLabel.setText(self.tr("Winner"))
        else:
            self.teamResultLabel.setText(self.tr("Loser"))

        self.towerKillsLabel.setText(str(towerKills))
        self.inhibitorKillsLabel.setText(str(inhibitorKills))
        self.baronKillsLabel.setText(str(baronKills))
        self.dragonKillsLabel.setText(str(dragonKills))
        self.riftHeraldKillsLabel.setText(str(riftHeraldKills))

        self.towerIconLabel.setPixmap(QPixmap(towerIcon).scaled(
            20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.inhibitorIconLabel.setPixmap(QPixmap(inhibitorIcon).scaled(
            16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.baronIconLabel.setPixmap(QPixmap(baronIcon).scaled(
            16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.dragonIconLabel.setPixmap(QPixmap(dragonIcon).scaled(
            16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.riftHeraldIconLabel.setPixmap(QPixmap(riftHeraldIcon).scaled(
            16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        self.dmgIconLabel.setText("DMG")

        color = "white" if isDarkTheme() else "black"
        self.goldIconLabel.setPixmap(QPixmap(f"app/resource/images/Gold_{color}.png").scaled(
            16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.csIconLabel.setPixmap(QPixmap(f"app/resource/images/Minions_{color}.png").scaled(
            16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        if len(bans) != 0:
            self.bansButton.setVisible(True)
            self.bansFlyOut = BansFlyoutView(bans)
        else:
            self.bansButton.setVisible(False)

        self.csIconLabel.setVisible(True)
        self.goldIconLabel.setVisible(True)

        self.kdaLabel.setText(f"{kills} / {deaths} / {assists}")

    def updateSummoners(self, summoners):
        for i in reversed(range(self.summonersLayout.count())):
            item = self.summonersLayout.itemAt(i)
            self.summonersLayout.removeItem(item)
            if item.widget():
                item.widget().deleteLater()

        for summoner in summoners:
            infoBar = SummonerInfoBar(summoner)

            self.summonersLayout.addWidget(infoBar)

        if len(summoners) != 5:
            self.summonersLayout.addSpacerItem(QSpacerItem(
                1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def __updateIconColor(self, theme: Theme):
        color = "white" if theme == Theme.DARK else "black"
        self.goldIconLabel.setPixmap(QPixmap(f"app/resource/images/Gold_{color}.png").scaled(
            16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.csIconLabel.setPixmap(QPixmap(f"app/resource/images/Minions_{color}.png").scaled(
            16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))


class BansFlyoutView(FlyoutViewBase):
    def __init__(self, bans, parent=None):
        super().__init__(parent)
        self.hBoxLayout = QHBoxLayout(self)

        for champion in bans:
            icon = RoundIcon(champion, 25, 0, 3)
            self.hBoxLayout.addWidget(icon)


class SummonerInfoBar(QFrame):
    def __init__(self, summoner, parent=None):
        super().__init__(parent)
        self.setFixedHeight(39)

        self.hBoxLayout = QHBoxLayout(self)
        self.runeIcon = QLabel()

        self.spellsLayout = QHBoxLayout()

        self.spell1Icon = QLabel()
        self.spell2Icon = QLabel()

        self.levelLabel = QLabel()
        self.championIconLabel = RoundIcon(summoner["championIcon"], 25, 0, 3)
        self.summonerName = SummonerName(summoner["summonerName"])

        self.rankIcon = QLabel()

        self.itemsLayout = QHBoxLayout()
        self.items = []

        self.kdaLabel = QLabel()
        self.csLabel = QLabel()
        self.goldLabel = QLabel()
        self.demageLabel = QLabel()

        self.__initWidget(summoner)
        self.__initLayout()

        self.summonerName.clicked.connect(lambda: self.parent(
        ).parent().summonerNameClicked.emit(summoner["puuid"]))

    def __initWidget(self, summoner):
        self.isCurrent = summoner["isCurrent"]
        if self.isCurrent:
            self.setObjectName("currentSummonerWidget")

        self.runeIcon.setPixmap(QPixmap(summoner["runeIcon"]).scaled(
            23, 23, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.spell1Icon.setFixedSize(18, 18)
        self.spell1Icon.setPixmap(QPixmap(summoner["spell1Icon"]).scaled(
            16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.spell2Icon.setFixedSize(18, 18)
        self.spell2Icon.setPixmap(QPixmap(summoner["spell2Icon"]).scaled(
            16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.spell1Icon.setStyleSheet(
            "QLabel {border: 1px solid rgb(70, 55, 20)}")
        self.spell2Icon.setStyleSheet(
            "QLabel {border: 1px solid rgb(70, 55, 20)}")

        self.levelLabel.setText(str(summoner["champLevel"]))
        self.levelLabel.setObjectName("levelLabel")
        self.levelLabel.setAlignment(Qt.AlignCenter)
        self.levelLabel.setFixedWidth(20)

        self.items = [QPixmap(icon).scaled(
            21, 21, Qt.KeepAspectRatio, Qt.SmoothTransformation) for icon in summoner["itemIcons"]]

        if summoner["rankInfo"]:
            if summoner['rankIcon'] != None:
                self.rankIcon.setPixmap(QPixmap(summoner["rankIcon"]).scaled(
                    30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.rankIcon.setFixedSize(30, 30)

                tier, divison, lp = summoner["tier"], summoner["division"], summoner["lp"]
                if tier != "":
                    self.rankIcon.setToolTip(f"{tier} {divison} {lp}")
                else:
                    self.rankIcon.setToolTip(self.tr("Unranked"))

                self.rankIcon.installEventFilter(
                    ToolTipFilter(self.rankIcon, 0, ToolTipPosition.TOP))
            else:
                self.rankIcon.setText(str(summoner['lp']))
                self.rankIcon.setFixedWidth(40)

        self.kdaLabel.setText(
            f"{summoner['kills']} / {summoner['deaths']} / {summoner['assists']}")
        self.kdaLabel.setFixedWidth(100)
        self.kdaLabel.setAlignment(Qt.AlignCenter)

        self.csLabel.setText(str(summoner["cs"]))
        self.csLabel.setAlignment(Qt.AlignCenter)
        self.csLabel.setFixedWidth(50)

        self.goldLabel.setText(str(summoner["gold"]))
        self.goldLabel.setAlignment(Qt.AlignCenter)
        self.goldLabel.setFixedWidth(60)

        self.demageLabel.setText(str(summoner["demage"]))
        self.demageLabel.setAlignment(Qt.AlignCenter)
        self.demageLabel.setFixedWidth(70)

    def __initLayout(self):
        self.spellsLayout.setContentsMargins(0, 0, 0, 0)
        self.spellsLayout.setSpacing(0)
        self.spellsLayout.addWidget(self.spell1Icon)
        self.spellsLayout.addWidget(self.spell2Icon)

        self.itemsLayout.setSpacing(0)
        self.spellsLayout.setContentsMargins(0, 0, 0, 0)
        for icon in self.items:
            itemLabel = QLabel()
            itemLabel.setPixmap(icon)
            itemLabel.setStyleSheet(
                "QLabel {border: 1px solid rgb(70, 55, 20)}")
            itemLabel.setFixedSize(23, 23)

            self.itemsLayout.addWidget(itemLabel)

        self.hBoxLayout.setContentsMargins(6, 0, 6, 0)
        self.hBoxLayout.addWidget(self.runeIcon)
        self.hBoxLayout.addLayout(self.spellsLayout)
        self.hBoxLayout.addWidget(self.levelLabel)
        self.hBoxLayout.addWidget(self.championIconLabel)
        self.hBoxLayout.addWidget(self.summonerName)
        self.hBoxLayout.addSpacing(10)
        self.hBoxLayout.addSpacerItem(QSpacerItem(
            1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(self.rankIcon)
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addLayout(self.itemsLayout)

        self.hBoxLayout.addWidget(self.kdaLabel)
        self.hBoxLayout.addWidget(self.csLabel)
        self.hBoxLayout.addWidget(self.goldLabel)
        self.hBoxLayout.addWidget(self.demageLabel)


class GameTitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(78)
        self.titleBarLayout = QHBoxLayout(self)
        self.infoLayout = QVBoxLayout()
        self.mapIcon = QLabel()
        self.resultLabel = QLabel()
        self.infoLabel = QLabel()
        self.copyGameIdButton = ToolButton(Icon.COPY)
        self.gameId = None

        self.__initWidget()
        self.__initLayout()
        self.__connectSignalToSlot()

    def __initWidget(self):
        self.resultLabel.setObjectName("resultLabel")
        self.infoLabel.setObjectName("infoLabel")
        self.copyGameIdButton.setVisible(False)
        self.copyGameIdButton.setFixedSize(36, 36)
        self.copyGameIdButton.setToolTip(self.tr("Copy game ID"))
        self.copyGameIdButton.installEventFilter(ToolTipFilter(
            self.copyGameIdButton, 500, ToolTipPosition.LEFT))

    def __initLayout(self):
        self.infoLayout.setSpacing(0)
        self.infoLayout.setContentsMargins(0, 4, 0, 6)
        self.infoLayout.addSpacing(-5)
        self.infoLayout.addWidget(self.resultLabel)
        self.infoLayout.addWidget(self.infoLabel)

        self.titleBarLayout.addWidget(self.mapIcon)
        self.titleBarLayout.addSpacing(5)
        self.titleBarLayout.addLayout(self.infoLayout)
        self.titleBarLayout.addSpacerItem(QSpacerItem(
            1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.titleBarLayout.addWidget(self.copyGameIdButton)
        self.titleBarLayout.addSpacing(10)

    def updateTitleBar(self, mapIcon, result, mapName, modeName, duration, creation, gameId, color):
        self.gameId = gameId
        self.mapIcon.setPixmap(mapIcon)
        self.resultLabel.setText(result)
        self.infoLabel.setText(
            f"{mapName}  ·  {modeName}  ·  {duration}  ·  {creation}  ·  " + self.tr("Game ID: ") + f"{gameId}")
        self.copyGameIdButton.setVisible(True)

        self.setStyleSheet(
            f""" GameTitleBar {{
            border-radius: 6px;
            border: 1px solid rgb({color});
            background-color: rgba({color}, 0.15);
        }}"""
        )

    def __connectSignalToSlot(self):
        self.copyGameIdButton.clicked.connect(
            lambda: pyperclip.copy(self.gameId))


class GamesView(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.hBoxLayout = QHBoxLayout(self)
        self.gamesTab = GamesTab()
        self.gameDetailView = GameDetailView()

        self.__initLayout()

    def __initLayout(self):
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.hBoxLayout.setSpacing(0)

        self.hBoxLayout.addWidget(self.gamesTab)
        self.hBoxLayout.addWidget(self.gameDetailView)


class GameTab(QFrame):
    def __init__(self, game=None, parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)
        self.setFixedWidth(141)
        self.setProperty("pressed", False)

        self.vBoxLayout = QHBoxLayout(self)
        self.nameTimeKdaLayout = QVBoxLayout()

        self.gameId = game["gameId"]
        self.championIcon = RoundIcon(game["championIcon"], 32, 2, 2)

        self.modeName = QLabel(game["name"].replace("排位赛 ", ""))

        self.time = QLabel(
            f"{game['shortTime']}  {game['kills']}/{game['deaths']}/{game['assists']}")
        self.resultLabel = QLabel()

        if game["remake"]:
            self.resultLabel.setText(self.tr("remake"))
        elif game["win"]:
            self.resultLabel.setText(self.tr("win"))
        else:
            self.resultLabel.setText(self.tr("lose"))

        self.__setColor(game["remake"], game["win"])

        self.__initWidget()
        self.__initLayout()

    def __initWidget(self):
        self.time.setObjectName("time")

    def __initLayout(self):
        self.nameTimeKdaLayout.addWidget(self.modeName)
        self.nameTimeKdaLayout.addWidget(self.time)

        self.vBoxLayout.addWidget(self.championIcon)
        self.vBoxLayout.addSpacing(2)
        self.vBoxLayout.addLayout(self.nameTimeKdaLayout)

        self.vBoxLayout.addSpacerItem(QSpacerItem(
            1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))

    def __setColor(self, remake=True, win=True):
        if remake:
            r, g, b = 162, 162, 162
        elif win:
            r, g, b = 57, 176, 27
        else:
            r, g, b = 211, 25, 12

        f1, f2 = 1.1, 0.8
        r1, g1, b1 = min(r * f1, 255), min(g * f1, 255), min(b * f1, 255)
        r2, g2, b2 = min(r * f2, 255), min(g * f2, 255), min(b * f2, 255)

        self.setStyleSheet(
            f""" GameTab {{
            border-radius: 6px;
            border: 1px solid rgb({r}, {g}, {b});
            background-color: rgba({r}, {g}, {b}, 0.15);
        }}
        GameTab:hover {{
            border-radius: 6px;
            border: 1px solid rgb({r1}, {g1}, {b1});
            background-color: rgba({r1}, {g1}, {b1}, 0.2);
        }}
        GameTab[pressed = true] {{
            border-radius: 6px;
            border: 1px solid rgb({r2}, {g2}, {b2});
            background-color: rgba({r2}, {g2}, {b2}, 0.25);
        }}"""
        )

    def mousePressEvent(self, a0) -> None:
        self.setProperty("pressed", True)
        self.style().polish(self)
        return super().mousePressEvent(a0)

    def mouseReleaseEvent(self, a0) -> None:
        self.setProperty("pressed", False)
        self.style().polish(self)

        self.parent().parent().parent().tabClicked.emit(str(self.gameId))
        return super().mouseReleaseEvent(a0)


class SearchInterface(SmoothScrollArea):
    summonerPuuidGetted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # self.filterData = (420, 440, 430, 450)  # 默认全选
        # self.filterTimer = threading.Timer(.5, self.__onSearchButtonClicked)
        # self.filterOld = None  # 条件改动前后若无变化, 则不触发更新逻辑

        self.games = []
        self.queueIdBuffer = {}
        self.loadGamesThread = None
        self.loadGamesThreadStop = threading.Event()

        self.vBoxLayout = QVBoxLayout(self)

        self.searchLayout = QHBoxLayout()
        self.searchLineEdit = LineEdit()
        self.searchButton = PushButton(self.tr("Search 🔍"))
        self.careerButton = PushButton(self.tr("Career"))
        self.filterComboBox = ComboBox()

        # self.filterButton = PushButton(self.tr("Filter"))
        # self.filterButton.clicked.connect(self.showFilterFlyout)

        self.gamesView = GamesView()
        self.currentSummonerName = None

        self.__initWidget()
        self.__initLayout()
        self.__connectSignalToSlot()

    def __initWidget(self):
        self.searchLineEdit.setAlignment(Qt.AlignCenter)
        self.searchLineEdit.setClearButtonEnabled(True)
        self.searchLineEdit.setPlaceholderText(
            self.tr("Please input summoner name"))
        self.careerButton.setEnabled(False)
        # self.filterButton.setEnabled(False)
        self.filterComboBox.setEnabled(False)

        self.searchButton.setShortcut("Return")

        StyleSheet.SEARCH_INTERFACE.apply(self)

        self.filterComboBox.addItems([
            self.tr('All'),
            self.tr('Normal'),
            self.tr("A.R.A.M."),
            self.tr("Ranked Solo"),
            self.tr("Ranked Flex")
        ])
        self.filterComboBox.setCurrentIndex(0)

    def __initLayout(self):
        self.searchLayout.addWidget(self.searchLineEdit)
        self.searchLayout.addSpacing(5)
        self.searchLayout.addWidget(self.searchButton)
        self.searchLayout.addWidget(self.careerButton)
        # self.searchLayout.addWidget(self.filterButton)
        self.searchLayout.addWidget(self.filterComboBox)

        self.vBoxLayout.addLayout(self.searchLayout)
        self.vBoxLayout.addSpacing(5)
        self.vBoxLayout.addWidget(self.gamesView)
        self.vBoxLayout.setContentsMargins(30, 32, 30, 30)

    def __onSearchButtonClicked(self):
        targetName = self.searchLineEdit.text()
        if targetName == "":
            return

        if self.loadGamesThread:
            self.loadGamesThreadStop.set()

        def _():
            try:
                summoner = connector.getSummonerByName(targetName)
                puuid = summoner["puuid"]
                self.currentSummonerName = targetName
                self.loadGamesThread = threading.Thread(target=self.loadGames, args=(puuid,))
                self.loadGamesThread.start()

                while len(self.games) < 10 and self.loadGamesThread.is_alive():
                    time.sleep(.1)

                self.careerButton.setEnabled(True)
                # self.filterButton.setEnabled(True)
                self.filterComboBox.setEnabled(True)
                self.gamesView.gameDetailView.clear()
                self.gamesView.gamesTab.triggerByButton = True
                self.gamesView.gamesTab.firstCall(puuid)
            except:
                # puuid = "-1"
                self.__showSummonerNotFoundMessage()

            # self.summonerPuuidGetted.emit(puuid)

        threading.Thread(target=_).start()

    def loadGames(self, puuid):
        """

        @warning 该方法会导致线程阻塞

        @param puuid:
        @return:
        """
        gameIdx = 0
        begIdx = 0
        endIdx = begIdx + 9
        while True:
            games = connector.getSummonerGamesByPuuid(
                puuid, begIdx, endIdx)

            for game in games["games"]:
                if time.time() - game['gameCreation'] / 1000 > 60 * 60 * 24 * 365:
                    return

                if self.loadGamesThreadStop.isSet():
                    self.games = []
                    self.loadGamesThreadStop.clear()
                    return

                self.games.append(processGameData(game))

                if self.queueIdBuffer.get(game["queueId"]):
                    self.queueIdBuffer[game["queueId"]].append(gameIdx)
                else:
                    self.queueIdBuffer[game["queueId"]] = [gameIdx]
                # self.queueIdBuffer[game["queueId"]] = self.queueIdBuffer.get(game["queueId"], []).append(gameIdx)

                gameIdx += 1

            begIdx = endIdx + 1
            endIdx += 9

    def __onSummonerPuuidGetted(self, puuid):
        if puuid != "-1":
            self.careerButton.setEnabled(True)
            # self.filterButton.setEnabled(True)
            self.filterComboBox.setEnabled(True)
            self.gamesView.gameDetailView.clear()
            self.gamesView.gamesTab.triggerByButton = True
            self.gamesView.gamesTab.updatePuuid(puuid)
        else:
            self.__showSummonerNotFoundMessage()

    def __connectSignalToSlot(self):
        self.searchButton.clicked.connect(self.__onSearchButtonClicked)
        self.summonerPuuidGetted.connect(self.__onSummonerPuuidGetted)

    def __showSummonerNotFoundMessage(self):
        InfoBar.error(
            title=self.tr("Summoner not found"),
            content=self.tr("Please check the summoner name and retry"),
            orient=Qt.Vertical,
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=5000,
            parent=self,
        )

    def setEnabled(self, a0: bool) -> None:
        self.gamesView.gamesTab.backToDefaultPage()
        self.gamesView.gameDetailView.clear()
        self.searchLineEdit.clear()

        self.searchLineEdit.setEnabled(a0)
        self.searchButton.setEnabled(a0)

        self.filterComboBox.setEnabled(a0)
        # self.filterButton.setEnabled(a0)

        return super().setEnabled(a0)

    def fillterTimerRun(self):
        if self.filterOld != self.filterData:
            self.__onSearchButtonClicked()

        self.filterOld = None

    def showFilterFlyout(self):
        filterFlyout = FlyoutView("", "")

        filterBoxGroup = ModeFilterWidget()
        filterBoxGroup.setCheckBoxState(self.filterData)

        def _():
            self.filterTimer.cancel()

            if not self.filterOld:
                self.filterOld = self.filterData

            # 将选中状态同步到 interface
            self.filterData = filterBoxGroup.getFilterMode()
            self.gamesView.gamesTab.currentIndex = 0

            # 消除频繁切换筛选条件带来的抖动
            self.filterTimer = threading.Timer(.7, lambda obj=self: obj.fillterTimerRun())
            self.filterTimer.start()

        filterBoxGroup.setCallback(_)

        filterFlyout.widgetLayout.addWidget(filterBoxGroup, 0, Qt.AlignCenter)

        filterFlyout.widgetLayout.setContentsMargins(1, 1, 1, 1)
        filterFlyout.widgetLayout.setAlignment(Qt.AlignCenter)

        filterFlyout.viewLayout.setSpacing(0)
        filterFlyout.viewLayout.setContentsMargins(1, 1, 1, 1)

        w = Flyout.make(filterFlyout, self.filterButton,
                        self.window(), FlyoutAnimationType.DROP_DOWN)
        filterFlyout.closed.connect(w.close)
