import math
import numpy as np
from external import igl
import OpenGL.GL as gl
from PySide import QtGui, QtCore
from material import BaseMaterial
from common import normalize


# this is to cache the unpack indices so we dont' have to regenerate
# refer to PolyMesh.unpackTriangles
UNPACK_TRIANGLES_COUNTMAPS = {}


class Branch(QtCore.QObject):

    drawSignal = QtCore.Signal((BaseMaterial, bool))
    updateSampleSignal = QtCore.Signal(int)
    accumXformSignal = QtCore.Signal(np.ndarray)

    def __init__(self, path, kind='Branch', isRoot=False, rootName='/'):
        super(Branch, self).__init__(parent=None)
        self.isRoot = isRoot
        if isRoot:
            self.name = rootName
            self.path = '/'
            self.map = {'/': self}
        else:
            self.path = path
            self.name = path.split('/')[-1]
            self.map = None

        self.visible = True
        self.alwaysVisible = False
        self.root = None
        self.parentPath = None
        self.childrenPaths = None
        self.kind = kind
        self.bbox = None
        self.matrix = np.identity(4).T

    @staticmethod
    def allParents(path):
        pathSplit = path.split('/')
        c = len(pathSplit) - 1
        retList = ['/'.join(pathSplit[:i - c]) for i in range(1, c)]
        retList.append('/')
        return retList

    @classmethod
    def iterateLeaves(cls, paths):
        skipParents = []
        for path in reversed(sorted(paths)):
            skipParents.extend(cls.allParents(path))
            if path in skipParents:
                continue
            yield path

    @staticmethod
    def isIdentity(arr):
        return np.array_equal(arr.reshape(4, 4), np.identity(4).T.reshape(4, 4))

    def accumXform(self, matrix):
        if self.isIdentity(self.matrix):
            self.matrix = matrix
        elif not self.isIdentity(matrix):
            self.matrix = np.dot(matrix.reshape(4, 4), self.matrix.reshape(4, 4))
        self.accumXformSignal.emit(self.matrix)

    def setupChild(self, parentPath, childPath):
        child = self.map[childPath]
        parent = self.map[parentPath]
        if parent.childrenPaths is None:
            parent.childrenPaths = [childPath]
            child.parentPath = parentPath
            child.accumXformSignal.connect(
                parent.accumXform
            )
        else:
            if childPath not in parent.childrenPaths:
                parent.childrenPaths.append(childPath)
                child.parentPath = parentPath
                child.accumXformSignal.connect(
                    parent.accumXform
                )

    def rootInit(self):
        if not self.isRoot:
            return
        for path, branch in self.map.iteritems():
            if path == '/':
                continue
            self.drawSignal.connect(branch.drawSlot)
            self.updateSampleSignal.connect(branch.updateSampleSlot)

        for leafPath in self.iterateLeaves(self.map.keys()):
            rsortedParentPaths = list(reversed(sorted(self.allParents(leafPath))))
            for i, parentPath in enumerate(rsortedParentPaths):
                if i < len(rsortedParentPaths) - 1:
                    self.setupChild(parentPath, rsortedParentPaths[i + 1])
                elif parentPath != leafPath:
                    self.setupChild(parentPath, leafPath)

        # signals children and expects them to propagate
        self.accumXformSignal.emit(self.matrix)

    def drawSlot(self, material, parentVisible):
        gl.glUseProgram(material.shaderProg)
        gl.glUniformMatrix4fv(
            gl.glGetUniformLocation(material.shaderProg, 'model'),
            1,
            gl.GL_FALSE,
            self.matrix
        )
        gl.glUseProgram(0)

        if self.isRoot:
            self.drawSignal.emit(material, parentVisible)  # signals all members

        self.visible = parentVisible or self.alwaysVisible
        self.draw(material)

    def updateSampleSlot(self, sampleIndex):
        if self.isRoot:
            self.updateSampleSignal.emit(sampleIndex)  # signals all members
        # TODO handle xform and bbox samples
        self.updateSample(sampleIndex)

    def draw(self, material):
        pass

    def updateSample(self, sampleIndex):
        pass


class Camera(Branch):

    cameraChangedSignal = QtCore.Signal((np.ndarray, np.ndarray))  # viewMatrix, projectionMatrix

    def __init__(self, path):
        super(Camera, self).__init__(path, 'Camera')

        self.fov = 30
        self.aspect = 1.
        self.near = .1
        self.far = 10000.
        self.theta = np.pi / 2.
        self.phi = np.pi / 2.
        self.radius = 300.
        self.upsign = 1.
        self.target = np.array([0., 0., 0.], np.float32)
        self.orbit(math.radians(-45), math.radians(-45))
        self.navigating = False

    def cameraChanged(self):
        self.cameraChangedSignal.emit(self.viewMatrix(), self.projectionMatrix())

    def cameraPosition(self):
        height = math.cos(self.phi) * self.radius
        distance = math.sin(self.phi) * self.radius

        return np.array([
            distance * math.cos(self.theta),
            height,
            distance * math.sin(self.theta)
        ]) + self.target

    def orbit(self, theta, phi):
        self.phi += phi

        twoPi = np.pi * 2.
        while self.phi > twoPi:
            self.phi -= twoPi
        while self.phi < -twoPi:
            self.phi += twoPi

        if (self.phi < np.pi and self.phi > 0.0):
            self.upsign = 1.0
        elif (self.phi < -np.pi and self.phi > -2 * np.pi):
            self.upsign = 1.0
        else:
            self.upsign = -1.0

        self.theta += self.upsign * theta
        self.cameraChanged()

    def pan(self, dx, dy):
        direction = normalize([self.target - self.cameraPosition()])[0]
        right = np.cross(direction, [0., self.upsign, 0.])
        up = np.cross(right, direction)

        self.target += right * dx
        self.target += up * dy
        self.cameraChanged()

    def zoom(self, distance):
        if self.radius - distance > 0:
            self.radius -= distance
        self.cameraChanged()

    def projectionMatrix(self):
        tempMat = QtGui.QMatrix4x4()
        tempMat.perspective(self.fov, self.aspect, self.near, self.far)
        return np.array(tempMat.data(), np.float32).reshape(4, 4)

    def viewMatrix(self):
        direction = normalize([self.target - self.cameraPosition()])[0]
        right = np.cross(direction, [0., self.upsign, 0.])
        up = np.cross(right, direction)
        eye = self.cameraPosition()

        tempMat = QtGui.QMatrix4x4()
        tempMat.lookAt(
            QtGui.QVector3D(*eye),
            QtGui.QVector3D(*self.target),
            QtGui.QVector3D(*up)
        )
        return np.array(tempMat.data(), np.float32).reshape(4, 4)

    def mouseMoveEvent(self, buttons, dx, dy):
        self.navigating = True
        if buttons == QtCore.Qt.LeftButton:
            self.orbit(
                -dx * 6.,
                dy * 6.
            )
        elif buttons == QtCore.Qt.MidButton:
            self.pan(
                dx * self.radius,
                -dy * self.radius
            )
        elif buttons == QtCore.Qt.RightButton:
            if abs(dx) > abs(dy):
                self.zoom(-dx * self.radius * 3.)
            else:
                self.zoom(dy * self.radius * 3.)
        else:
            self.navigating = False

    def wheelEvent(self, event):
        if (event.modifiers() & QtCore.Qt.ControlModifier):
            # TODO fov, focal length
            pass
        else:
            self.zoom(event.delta() * (self.radius / 1000.))


class PolyMesh(Branch):
    def __init__(self, path):
        super(PolyMesh, self).__init__(path, 'PolyMesh')
        self.triCount = None
        self.trimap = None

        # these are going to be consumed on unpackTriangles
        # as they turn into buffers
        self.indices = None
        self.counts = None
        self.points = None

        # this is the sample property for points from alembic
        self.pointProp = None

        self.vao = None
        self.vboVerts = None
        self.vboIndices = None

        self.initialized = False

    def prepMesh(self):
        # TODO make trimap as well so we can unpack samples with it
        trimap = []

        dif = np.where(np.diff(self.counts) > 0)[0] + 1
        if len(dif) == 0 and self.counts[0] > 3:
            count = self.counts[0]
            countkey = str(count)
            if countkey not in UNPACK_TRIANGLES_COUNTMAPS:
                a = np.arange(count, dtype=np.uint32)
                first = a[:3]
                rest = a[3:]
                shift = rest - 1
                zero = np.zeros(rest.shape[0], dtype=np.uint32)
                UNPACK_TRIANGLES_COUNTMAPS[countkey] = np.append(
                    first,
                    np.append(
                        zero,
                        np.append(
                            shift, rest
                        )
                    ).reshape(-1, count - 3).T
                )
            cmap = UNPACK_TRIANGLES_COUNTMAPS[countkey]
            trimap.extend(self.indices.reshape(-1, count)[:, cmap].flatten().tolist())
        elif len(dif) == 0 and self.counts[0] == 3:
            trimap = self.indices
        elif len(dif) != 0 and self.counts[0] > 2:
            indicesLen = self.indices.shape[0]
            self.indices = np.array(
                np.split(
                    self.indices,
                    np.cumsum(self.counts)[:-1]
                )
            )

            cursor = 0
            for end in np.append(dif, indicesLen):
                count = self.counts[cursor]
                if count > 3:
                    countkey = str(count)
                    if countkey not in UNPACK_TRIANGLES_COUNTMAPS:
                        a = np.arange(count, dtype=np.uint32)
                        first = a[:3]
                        rest = a[3:]
                        shift = rest - 1
                        zero = np.zeros(rest.shape[0], dtype=np.uint32)
                        UNPACK_TRIANGLES_COUNTMAPS[countkey] = np.append(
                            first,
                            np.append(
                                zero,
                                np.append(
                                    shift, rest
                                )
                            ).reshape(-1, count - 3).T
                        )
                    cmap = UNPACK_TRIANGLES_COUNTMAPS[countkey]
                    pinds = np.hstack(self.indices[cursor:end].flat)
                    trimap.extend(pinds.reshape(-1, count)[:, cmap].flatten().tolist())
                elif count == 3:
                    pinds = np.hstack(self.indices[cursor:end].flat)
                    trimap.extend(pinds.tolist())
                else:
                    pass  # TODO ? draw lines or points ?

                cursor = end
        else:
            pass  # TODO ? draw lines or points ?

        self.trimap = np.array(trimap, np.uint32).reshape(-1, 3)
        self.triCount = self.trimap.shape[0] * 3

        self.V = igl.eigen.MatrixXd(self.points.astype(float).tolist())
        self.F = igl.eigen.MatrixXi(self.trimap.astype(int).tolist())

        del self.indices
        del self.counts
        self.indices = None
        self.counts = None

    def init(self):
        if self.initialized:
            return

        self.prepMesh()

        self.vao = gl.glGenVertexArrays(1)
        gl.glBindVertexArray(self.vao)

        self.vboIndices = gl.glGenBuffers(1)
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self.vboIndices)
        gl.glBufferData(
            gl.GL_ELEMENT_ARRAY_BUFFER,
            self.trimap.nbytes,
            self.trimap,
            gl.GL_DYNAMIC_DRAW
        )

        self.vboVerts = gl.glGenBuffers(1)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vboVerts)
        gl.glBufferData(
            gl.GL_ARRAY_BUFFER,
            self.points.nbytes,
            self.points,
            gl.GL_DYNAMIC_DRAW
        )

        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, 0)
        gl.glBindVertexArray(0)

        self.initialized = True

    def draw(self, material):
        if self.vao is None:
            return

        if self.visible:
            gl.glUseProgram(material.shaderProg)
            gl.glBindVertexArray(self.vao)

            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self.vboIndices)

            gl.glEnableVertexAttribArray(0)
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vboVerts)
            gl.glVertexAttribPointer(
                0,
                3,
                gl.GL_FLOAT,
                gl.GL_FALSE,
                0,
                None
            )

            gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_FILL)
            gl.glDrawElements(
                gl.GL_TRIANGLES,
                self.triCount,
                gl.GL_UNSIGNED_INT,
                None
            )

            gl.glDisableVertexAttribArray(0)
            gl.glDisableVertexAttribArray(1)
            gl.glBindVertexArray(0)
            gl.glUseProgram(0)

    def updateSample(self, sampleIndex):
        if not self.initialized:
            self.init()
        if self.pointProp.getNbStoredSamples() == 1:
            return
        if sampleIndex >= self.pointProp.getNbStoredSamples():
            sampleIndex = self.pointProp.getNbStoredSamples() - 1
        elif sampleIndex < 0:
            sampleIndex = 0

        self.points = np.array(
            self.pointProp.getValues(sampleIndex),
            np.float32
        ).reshape(-1, 3)

        gl.glBindVertexArray(self.vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vboVerts)
        gl.glBufferSubData(
            gl.GL_ARRAY_BUFFER,
            0,
            self.points.nbytes,
            self.points,
        )

        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glBindVertexArray(0)

    def updatePoints(self):
        if not self.initialized:
            self.init()

        gl.glBindVertexArray(self.vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vboVerts)
        gl.glBufferSubData(
            gl.GL_ARRAY_BUFFER,
            0,
            self.points.nbytes,
            self.points,
        )

        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glBindVertexArray(0)
