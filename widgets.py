from PySide import QtCore, QtGui, QtOpenGL
from loader import rootFromAlembic
from app import App


class Viewer(QtOpenGL.QGLWidget):

    initSignal = QtCore.Signal()
    drawSignal = QtCore.Signal()
    updateSampleSignal = QtCore.Signal(int)

    def __init__(self, parent=None):
        # at the time of writing latest OpenGL version is 4.5
        # TODO maybe make it smarter to fallback and such
        glformat = QtOpenGL.QGLFormat()
        glformat.setVersion(4, 5)
        glformat.setProfile(QtOpenGL.QGLFormat.CoreProfile)
        super(Viewer, self).__init__(
            glformat,
            parent
        )
        self.makeCurrent()

        self.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.setMouseTracking(True)

        self.oldmx = 0.
        self.oldmy = 0.

        self.app = App(self, [0, 0, self.width(), self.height()])

        self.initSignal.connect(self.app.initSlot)
        self.drawSignal.connect(self.app.drawSlot)
        self.updateSampleSignal.connect(self.app.updateSampleSlot)

        self.isPlaying = False
        self.playbackRange = (0, 200)
        self.currentFrame = 0
        self.showFrame(self.currentFrame)
        self.fpsLimit = 24.
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.forward = True
        self.timer.timeout.connect(self.adjustFrame)
        self.setCursor(QtCore.Qt.CrossCursor)

    def changeSelectedPath(self, path):
        branch = self.app.root.map[path]
        if branch.kind == 'PolyMesh':
            self.app.setActiveMesh(branch)
        else:
            self.app.setActiveMesh(None)

    def togglePlay(self, forward=True):
        self.isPlaying = not self.isPlaying
        if self.isPlaying:
            self.timer.start(1000. / self.fpsLimit)
        else:
            self.timer.stop()

    def adjustFrame(self, frame=None):
        if frame is not None:
            self.currentFrame = frame
        if self.isPlaying and self.forward:
            self.currentFrame += 1
        elif self.isPlaying:
            self.currentFrame -= 1

        if self.currentFrame > self.playbackRange[1]:
            self.currentFrame = self.playbackRange[0]
        elif self.currentFrame < self.playbackRange[0]:
            self.currentFrame = self.playbackRange[1]

        self.showFrame()

    def showFrame(self, frame=None):
        # TODO convert frame to sample indices
        if frame is not None:
            self.updateSampleSignal.emit(int(frame))
        else:
            self.updateSampleSignal.emit(int(self.currentFrame))

    def setRoot(self, root):
        self.app.setRoot(root)
        self.updateSampleSignal.emit(int(self.currentFrame))

    def initializeGL(self):
        self.initSignal.emit()

    def resizeGL(self, w, h):
        self.app.resize([0, 0, w, h])

    def paintGL(self, *args):
        self.drawSignal.emit()

    def mouseMoveEvent(self, event):
        width = self.width()
        height = self.height()
        pixelX = event.pos().x()
        pixelY = event.pos().y()
        dx = float(self.oldmx - pixelX)
        dy = float(self.oldmy - pixelY)
        self.oldmx = pixelX
        self.oldmy = pixelY
        dx /= width
        dy /= height

        hit = False
        if event.modifiers() != QtCore.Qt.AltModifier and not self.app.currentCamera.navigating:
            hit = self.app.currentBrush.mouseMoveEvent(
                event.pos().x(), event.pos().y(),
                event.modifiers(), event.buttons(),
                self.app.viewportCoords,
                self.app.currentCamera.viewMatrix(),
                self.app.currentCamera.projectionMatrix(),
                self.app.currentCamera.cameraPosition(),
                self.app.currentCamera.upsign,
                dx, dy
            )
        if (not hit or self.app.currentCamera.navigating) and not self.app.currentBrush.operating:
            self.app.currentCamera.mouseMoveEvent(event.buttons(), dx, dy)

        self.app.updateHit()
        self.update()

    def mousePressEvent(self, event):
        if event.modifiers() != QtCore.Qt.AltModifier and not self.app.currentCamera.navigating:
            self.app.currentBrush.handleMouseButton(
                event.pos().x(), event.pos().y(),
                event.modifiers(), event.buttons(),
                0, 0
            )

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Space:
            menu = QtGui.QMenu(self)
            rubberAction = menu.addAction('Rubber')
            defaultAction = menu.addAction('Default')
            action = menu.exec_(self.mapToGlobal(QtCore.QPoint(self.oldmx, self.oldmy)))
            if action == defaultAction:
                self.app.setMode('default')
            elif action == rubberAction:
                self.app.setMode('rubber')

    def wheelEvent(self, event):
        self.app.currentCamera.wheelEvent(event)


class ObjectTree(QtGui.QTreeView):

    pathSelectedSignal = QtCore.Signal(str)

    def __init__(self, *args):
        super(ObjectTree, self).__init__(*args)

    def selectionChanged(self, *args):
        index = self.selectedIndexes()[0]
        path = index.model().itemFromIndex(index).data(QtCore.Qt.UserRole)
        self.pathSelectedSignal.emit(str(path))

    def addRoot(self, root):
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        model = QtGui.QStandardItemModel()
        model.setHorizontalHeaderLabels(['Objects'])
        self.setModel(model)
        self.setUniformRowHeights(True)

        parents = {}
        for path in sorted(root.map.keys()):
            branch = root.map[path]
            parentPath = '/' + '/'.join(path.split('/')[1:-1])
            if parentPath not in parents:
                parent = QtGui.QStandardItem(branch.name)
                parent.setData(path, role=QtCore.Qt.UserRole)
                parents[path] = parent
                model.appendRow(parent)
            else:
                child = QtGui.QStandardItem(branch.name)
                child.setData(path, role=QtCore.Qt.UserRole)
                parents[path] = child
                parents[parentPath].appendRow([child])


class MainWindow(QtGui.QMainWindow):
    def __init__(self, *args):
        super(MainWindow, self).__init__(*args)

        self.setStyleSheet(stylesheet)

        self.setWindowTitle('Makina')
        self.setMinimumSize(864, 486)

        centralWidget = QtGui.QWidget()
        self.setCentralWidget(centralWidget)
        layout = QtGui.QGridLayout()
        centralWidget.setLayout(layout)

        self.objectTree = ObjectTree()
        layout.addWidget(self.objectTree, 0, 0)

        self.viewer = Viewer()
        layout.addWidget(self.viewer, 0, 1)
        layout.setColumnStretch(1, 100)

        self.objectTree.pathSelectedSignal.connect(self.viewer.changeSelectedPath)

    def loadAlembic(self, filePath):
        root = rootFromAlembic(filePath)
        self.viewer.setRoot(root)
        self.objectTree.addRoot(root)


# TODO
# modified from
# https://raw.githubusercontent.com/zyantific/IDASkins/master/skin/idaskins-dark/stylesheet.qss
stylesheet = '''
QWidget {
    background-color: #363636;
    color: #ddd;
}

QCheckBox {
    background-color: rgba(0, 0, 0, 0);
}

QTextEdit {
    background-color: #2d2d2d;
    border: 1px solid #363636;
    border-radius: 2px;
}

QMenuBar, QMenuBar::item {
    background-color: #444444;
    color: #ddd;
}

QMenu::item:selected {
    background-color: #2A2A2A;
}

QLineEdit {
    border: 1px solid #474747;
    min-height: 20px;
    border-radius: 2px;
}

QLineEdit:hover, QLineEdit:focus {
    border: 1px solid #00aaaa;
}

QTabBar::tab {
    background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #555555, stop: 1 #444444);
}

QTabBar::tab:selected {
    background-color: #777777;
}

QHeaderView::section {
    background-color: #444;
    border-left: 3px solid #666;
}

QTableView {
    border: 1px solid #474747;
    background-color: #2d2d2d;
}

QTableCornerButton::section {
    background: #222;
    border: 2px outset #222;
}

QScrollBar {
    background-color: #363636;
    width: 20px;
    height: 20px;
    margin: 0 0 0 0;
}

QScrollBar::sub-line, QScrollBar::add-line {
    width: 0;
    height: 0;
}

QScrollBar::add-page, QScrollBar::sub-page {
    background: none;
}

QScrollBar::handle:vertical {
    min-height: 20px;
}

QScrollBar::handle:horizontal {
    min-width: 20px;
}

QScrollBar::handle {
    background-color: #585858;
    margin: 3px;
    border-radius: 7px;
}

QToolBar {
    border: none;
}

QPushButton {
    border: 1px solid #077;
    text-align: center;
    min-height: 20px;
    min-width: 50px;
    padding: 0 6px 0 6px;
    border-radius: 2px;
}

QPushButton:hover, QPushButton:default {
    border: 1px solid #0aa;
}

QPushButton:pressed {
    border: 1px solid #0ee;
}

QComboBox {
    border: 1px solid #474747;
    border-radius: 2px;
}

QComboBox > QLineEdit, QComboBox > QLineEdit:hover, QComboBox > QLineEdit:focus {
    border: none;
    min-height: default;
}

QComboBox:hover, QComboBox:focus {
    border: 1px solid #00aaaa;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 15px;

    border-left-width: 1px;
    border-left-color: #666;
    border-left-style: solid;
}

QRadioButton, QLabel, QCheckBox {
    background: transparent;
}

QGroupBox {
    margin-top: 5px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
}

QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {
    background-color: #474747;
    color: #ddd;
}

QToolTip, QTipLabel {
    border: 1px solid #AA5500;
    border-radius: 3px;
    background: #111111;
    color: #ddd;
    margin: 0;
    padding: 0;
}
'''
