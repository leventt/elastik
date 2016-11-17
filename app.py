import os
import OpenGL.GL as gl
import numpy as np
from PySide import QtCore
from objects import Camera
import material
from loader import loadTexture
import controls


class App(QtCore.QObject):

    drawSignal = QtCore.Signal((material.BaseMaterial, bool))
    updateSampleSignal = QtCore.Signal(int)

    def __init__(self, viewer, viewportCoords=None):
        super(App, self).__init__()

        self.viewer = viewer
        if viewportCoords is not None:
            self.viewportCoords = viewportCoords
        else:
            self.viewportCoords = [0, 0, self.viewer.width(), self.viewer.height()]

        self.root = None

        self.drawGrid = False
        self.grid = Grid()
        self.brushes = {
            'default': controls.BrushBase(),
            'rubber': controls.RubberBrush()
        }
        for brush in self.brushes.values():
            brush.init()

        self.currentBrush = self.brushes['default']
        self.activeMesh = None

        self.material = material.MatcapMaterial()

        self.interactiveCamera = Camera('/interactiveCamera')
        self.interactiveCamera.aspect = self.viewportCoords[2] / float(self.viewportCoords[3])
        self.interactiveCamera.cameraChangedSignal.connect(self.updateViewProjection)
        self.currentCamera = self.interactiveCamera

    def setActiveMesh(self, activeMesh):
        self.activeMesh = activeMesh
        self.currentBrush.setActiveMesh(activeMesh)

    def setMode(self, mode):
        radius = self.currentBrush.radius
        if mode == 'default':
            self.currentBrush = self.brushes['default']
            self.currentBrush.updateRadius(radius)
        elif mode == 'rubber':
            self.currentBrush = self.brushes['rubber']
            self.currentBrush.updateRadius(radius)
        self.currentBrush.setActiveMesh(self.activeMesh)
        self.currentCamera.cameraChanged()
        self.viewer.update()

    def setRoot(self, root):
        root.rootInit()
        self.drawSignal.connect(root.drawSlot)
        self.updateSampleSignal.connect(root.updateSampleSlot)
        self.root = root

    def resize(self, viewportCoords=None):
        if viewportCoords is not None:
            self.viewportCoords = viewportCoords
        gl.glViewport(*self.viewportCoords)

        self.currentCamera.aspect = self.viewportCoords[2] / float(self.viewportCoords[3])
        self.currentCamera.cameraChanged()

    def updateViewProjection(self, view, projection):
        gl.glUseProgram(self.grid.material.shaderProg)
        gl.glUniformMatrix4fv(
            gl.glGetUniformLocation(self.grid.material.shaderProg, 'view'),
            1,
            gl.GL_FALSE,
            view
        )
        gl.glUniformMatrix4fv(
            gl.glGetUniformLocation(self.grid.material.shaderProg, 'projection'),
            1,
            gl.GL_FALSE,
            projection
        )
        gl.glUseProgram(0)
        self.currentBrush.updateViewProjection(view, projection)
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

        self.viewer.update()

    def initSlot(self):
        self.grid.init()
        self.currentBrush.init()
        self.init()

    def drawSlot(self):
        self.draw()

    def updateSampleSlot(self, sampleIndex):
        self.updateSampleSignal.emit(sampleIndex)
        self.updateSample(sampleIndex)

    def init(self):
        gl.glFrontFace(gl.GL_CW)
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glDepthFunc(gl.GL_LESS)
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        gl.glHint(gl.GL_POINT_SMOOTH_HINT, gl.GL_NICEST)
        gl.glEnable(gl.GL_VERTEX_PROGRAM_POINT_SIZE)

        gl.glClearColor(.212, .212, .212, 1)
        gl.glViewport(*self.viewportCoords)

        thisDir = os.getcwd()
        gl.glUseProgram(self.material.shaderProg)
        texLoc = gl.glGetUniformLocation(self.material.shaderProg, 'matcap')
        loadTexture(gl.GL_TEXTURE1, os.path.join(thisDir, 'res', 'matcap.png'))
        gl.glUniform1i(texLoc, 1)
        gl.glUseProgram(0)

    def draw(self):
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

        if self.drawGrid:
            self.grid.draw()

        self.drawSignal.emit(self.material, True)
        self.currentBrush.draw()

    def updateHit(self):
        gl.glUseProgram(self.material.shaderProg)
        if not self.currentBrush.active:
            gl.glUniform3f(
                gl.glGetUniformLocation(self.material.shaderProg, 'hitPos'),
                -1000., -1000., -1000.
            )
            gl.glUniform1f(
                gl.glGetUniformLocation(self.material.shaderProg, 'hitRadius'),
                0.
            )
        else:
            gl.glUniform3f(
                gl.glGetUniformLocation(self.material.shaderProg, 'hitPos'),
                *self.currentBrush.lastHit
            )
            gl.glUniform1f(
                gl.glGetUniformLocation(self.material.shaderProg, 'hitRadius'),
                float(self.currentBrush.radius)
            )
        gl.glUseProgram(0)

    def updateSample(self, sampleIndex):
        pass


class Grid(QtCore.QObject):
    def __init__(self, color=[1., 1., 1., .23]):
        coords = np.arange(-50, 51, 10)
        grid = []
        for v in coords:
            grid.extend([v, 0, coords[0]])
            grid.extend([v, 0, coords[-1]])
            grid.extend([coords[0], 0, v])
            grid.extend([coords[-1], 0, v])
        # this is going to be consumed on init
        self.verts = np.array(grid, np.float32)
        # :{ #
        self.count = self.verts.shape[0]
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
            gl.GL_STATIC_DRAW
        )

        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glBindVertexArray(0)

        del self.verts
        self.verts = None

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

        gl.glDrawArrays(
            gl.GL_LINES,
            0,
            self.count
        )

        gl.glDisableVertexAttribArray(0)

        gl.glBindVertexArray(0)
        gl.glUseProgram(0)
