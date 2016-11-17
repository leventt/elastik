import numpy as np
from PySide import QtCore
from external import igl
from common import normalize


class Rubber(QtCore.QObject):
    def __init__(self, *args):
        super(Rubber, self).__init__(*args)

        self.arapData = None
        self.pinVertIDs = []
        self.pinCoords = []
        self.activeMesh = None

    def preCompute(self):
        if len(self.pinVertIDs) <= 1 or self.activeMesh is None:
            return

        self.arapData = igl.ARAPData()

        arapPins = igl.eigen.MatrixXi(self.pinVertIDs)
        self.arapData.max_iter = 1
        igl.arap_precomputation(self.activeMesh.V, self.activeMesh.F, 3, arapPins, self.arapData)

    def appendPin(self, vertID, pinPos):
        self.pinVertIDs.append([vertID])
        self.pinCoords.append(pinPos)
        self.preCompute()

    def solveDelta(self, pinIndex, dx, dy, cameraPosition, upsign):
        if len(self.pinCoords) <= 0 or self.activeMesh is None:
            return

        arapMove = np.array(self.pinCoords[pinIndex])
        direction = normalize([np.array(self.pinCoords[pinIndex]) - cameraPosition])[0]
        right = np.cross(direction, [0., upsign, 0.])
        up = np.cross(right, direction)

        arapMove += right * -dx * 100.
        arapMove += up * dy * 100.

        self.pinCoords[pinIndex] = arapMove.astype(float).tolist()

        U = igl.eigen.MatrixXd(self.activeMesh.points.astype(float).tolist())
        igl.arap_solve(igl.eigen.MatrixXd(self.pinCoords), self.arapData, U)
        self.activeMesh.V = U
        self.activeMesh.points = np.array(U, np.float32, order='C', copy=True)
        self.activeMesh.updatePoints()
