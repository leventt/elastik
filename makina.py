import sys
import os
from widgets import MainWindow as mkWindow
from PySide import QtGui


if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    app.setStyle('fusion')
    wnd = mkWindow()
    wnd.show()

    thisDir = os.getcwd()
    wnd.loadAlembic(os.path.join(thisDir, 'res', 'hunter.abc'))

    sys.exit(app.exec_())
