import OpenGL.GL as gl
import numpy as np
from PySide import QtCore, QtGui
import material
from external import igl
from common import normalize
import operators


class BrushBase(QtCore.QObject):
    def __init__(self, radius=10., *args):
        super(BrushBase, self).__init__(*args)
        self.radius = radius

        self.lastHit = None
        self.lastHitID = None
        self.activeMesh = None

        self.active = False
        self.adjustingRadius = False
        self.operating = False
        self.alternative = False
        self.matrix = None

    def setActiveMesh(self, activeMesh):
        self.activeMesh = activeMesh

    def init(self):
        pass

    def updateViewProjection(self, view, projection):
        pass

    def updateRadius(self, radius):
        self.radius = radius

    def mouseMove(self):
        pass
        # TODO tidy up event handling

    def mousePress(self):
        pass
        # TODO tidy up event handling

    def handleMouseButton(self, x, y, modifiers, buttons, dx, dy):
        self.operating = False
        if buttons == QtCore.Qt.LeftButton:
            if modifiers == QtCore.Qt.ControlModifier:
                self.alternative = True
        elif buttons == QtCore.Qt.MidButton:
            self.adjustingRadius = True
            self.operating = True
            if abs(dx) > abs(dy):
                self.updateRadius(self.radius + -dx * self.radius * 3.)
            else:
                self.updateRadius(self.radius + dy * self.radius * 3.)
        else:
            self.operating = False
            self.adjustingRadius = False

    def mouseMoveEvent(self, x, y, modifiers, buttons, viewportCoords, viewMatrix, projectionMatrix, cameraPosition, upsign, dx, dy):
        if self.activeMesh is None:
            return False

        if self.adjustingRadius:
            self.handleMouseButton(x, y, modifiers, buttons, dx, dy)
            return False

        mX = float(x)
        mY = float(viewportCoords[3] - y)

        model = igl.eigen.MatrixXd(self.activeMesh.matrix.T.astype(float).tolist())
        view = igl.eigen.MatrixXd(viewMatrix.T.astype(float).tolist())
        projection = igl.eigen.MatrixXd(projectionMatrix.T.astype(float).tolist())
        viewport = igl.eigen.MatrixXd(map(float, viewportCoords))

        barycentricCoords = igl.eigen.MatrixXd()

        # Cast a ray in the view direction starting from the mouse position
        hitIDs = igl.eigen.MatrixXi([-1])
        coord = igl.eigen.MatrixXd([mX, mY])
        hit = igl.unproject_onto_mesh(coord, view * model, projection, viewport, self.activeMesh.V, self.activeMesh.F, hitIDs, barycentricCoords)

        hitID = hitIDs[0, 0]
        if hit and hitID != -1:
            face = self.activeMesh.points[self.activeMesh.trimap[hitID]] + self.activeMesh.offsets[self.activeMesh.trimap[hitID]]
            hitPos = face[0] * barycentricCoords[0] + face[1] * barycentricCoords[1] + face[2] * barycentricCoords[2]
            self.lastHit = hitPos.astype(float).tolist()
            self.lastHitID = int(self.activeMesh.trimap[hitID][0])
            self.lastHitNormal = normalize(np.cross(face[1] - face[0], face[2] - face[0]))[0]
            self.active = True

            tempMat = QtGui.QMatrix4x4()
            tempMat.translate(*self.lastHit)
            tempMat.rotate(QtGui.QQuaternion(1., 0., 0., -1.).normalized())
            tempMat.rotate(QtGui.QQuaternion(1. / np.linalg.norm(self.lastHitNormal), *self.lastHitNormal).normalized())
            self.matrix = np.array(tempMat.data(), np.float32).reshape(4, 4)
        else:
            self.active = False

        if hit:
            self.handleMouseButton(x, y, modifiers, buttons, dx, dy)
        else:
            self.operating = False
            self.alternative = False

        return hit

    def draw(self):
        pass


class PinPoint(QtCore.QObject):
    def __init__(self, color=[1., 0., 0., 1.], *args):
        super(PinPoint, self).__init__(*args)
        self.verts = np.array([0, 0, 0], np.float32)
        self.count = 1
        self.matrix = np.identity(4).T.reshape(4, 4)

        self.vao = None
        self.vboVerts = None

        self.material = material.ConstantMaterial()
        self.color = color

    def init(self):
        self.vao = gl.glGenVertexArrays(1)
        gl.glBindVertexArray(self.vao)

        self.vboVerts = gl.glGenBuffers(1)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vboVerts)
        gl.glBufferData(
            gl.GL_ARRAY_BUFFER,
            self.verts.nbytes,
            self.verts,
            gl.GL_DYNAMIC_DRAW
        )

        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glBindVertexArray(0)

        del self.verts
        self.verts = None

    def updateViewProjection(self, view, projection):
        gl.glUseProgram(self.material.shaderProg)
        gl.glUniformMatrix4fv(
            gl.glGetUniformLocation(self.material.shaderProg, 'view'),
            1,
            gl.GL_FALSE,
            view
        )
        gl.glUniformMatrix4fv(
            gl.glGetUniformLocation(self.material.shaderProg, 'projection'),
            1,
            gl.GL_FALSE,
            projection
        )
        gl.glUseProgram(0)

    def draw(self):
        gl.glUseProgram(self.material.shaderProg)

        gl.glBindVertexArray(self.vao)

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

        gl.glUniformMatrix4fv(
            gl.glGetUniformLocation(self.material.shaderProg, 'model'),
            1,
            gl.GL_FALSE,
            self.matrix
        )

        gl.glUniform4f(
            gl.glGetUniformLocation(self.material.shaderProg, 'inputColor'),
            *self.color
        )

        gl.glDisable(gl.GL_DEPTH_TEST)
        gl.glDrawArrays(
            gl.GL_POINTS,
            0,
            self.count
        )
        gl.glEnable(gl.GL_DEPTH_TEST)

        gl.glDisableVertexAttribArray(0)

        gl.glBindVertexArray(0)
        gl.glUseProgram(0)


class RubberBrush(BrushBase):
    def __init__(self, radius=10., *args):
        super(RubberBrush, self).__init__(radius, *args)
        self.cursorPin = PinPoint()
        self.pins = []
        self.view = None
        self.projection = None
        self.operator = operators.Rubber()
        self.pinInfo = []

    def setActiveMesh(self, activeMesh):
        super(RubberBrush, self).setActiveMesh(activeMesh)
        self.operator.activeMesh = activeMesh

    def init(self):
        super(RubberBrush, self).init()
        self.cursorPin.init()

    def updateViewProjection(self, view, projection):
        super(RubberBrush, self).updateViewProjection(view, projection)
        self.cursorPin.updateViewProjection(view, projection)
        for pin in self.pins:
            pin.updateViewProjection(view, projection)
        self.view = view
        self.projection = projection

    def updateRadius(self, radius):
        super(RubberBrush, self).updateRadius(radius)

    # TODO: i need press and release events
    def handleMouseButton(self, x, y, modifiers, buttons, dx, dy):
        super(RubberBrush, self).handleMouseButton(x, y, modifiers, buttons, dx, dy)
        if not self.active:
            return

        if self.alternative and self.view is not None and self.projection is not None:
            newPin = PinPoint()
            newPin.init()
            tempMat = QtGui.QMatrix4x4()
            tempMat.translate(*self.lastHit)
            tempMat.rotate(QtGui.QQuaternion(1., 0., 0., -1.).normalized())
            tempMat.rotate(QtGui.QQuaternion(1. / np.linalg.norm(self.lastHitNormal), *self.lastHitNormal).normalized())
            newPin.matrix = np.array(tempMat.data(), np.float32).reshape(4, 4)
            newPin.updateViewProjection(self.view, self.projection)
            newPin.draw()
            self.pins.append(newPin)

            self.operator.appendPin(self.lastHitID, self.lastHit)
            self.alternative = False

    def mouseMoveEvent(self, x, y, modifiers, buttons, viewportCoords, viewMatrix, projectionMatrix, cameraPosition, upsign, dx, dy):
        hit = super(RubberBrush, self).mouseMoveEvent(x, y, modifiers, buttons, viewportCoords, viewMatrix, projectionMatrix, cameraPosition, upsign, dx, dy)
        self.cursorPin.matrix = self.matrix

        self.operating = False
        if buttons == QtCore.Qt.LeftButton and not self.alternative:
            self.operator.solveDelta(-1, dx, dy, cameraPosition, upsign)
            self.operating = True

            vertID = self.operator.pinVertIDs[-1][0]
            tempMat = QtGui.QMatrix4x4()
            tempMat.translate(*(self.activeMesh.points[vertID] + self.activeMesh.offsets[vertID]))
            tempMat.rotate(QtGui.QQuaternion(1., 0., 0., -1.).normalized())
            tempMat.rotate(QtGui.QQuaternion(1. / np.linalg.norm(self.lastHitNormal), *self.lastHitNormal).normalized())
            self.pins[-1].matrix = np.array(tempMat.data(), np.float32).reshape(4, 4)
        if buttons == QtCore.Qt.MidButton:
            self.operating = True
            self.adjustingRadius = True

        return hit

    def draw(self):
        if (self.active and not self.operating) or self.adjustingRadius:
            self.cursorPin.draw()
        for pin in self.pins:
            pin.draw()
