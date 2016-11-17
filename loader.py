import os
import numpy as np
from PIL import Image
from external import alembic
import OpenGL.GL as gl
from objects import Branch, PolyMesh, Camera


def loadTexture(texEnum, filePath):
    pixels = np.asarray(Image.open(filePath).convert('RGBA'), dtype=np.uint8)

    texid = gl.glGenTextures(1)
    gl.glActiveTexture(texEnum)
    gl.glBindTexture(gl.GL_TEXTURE_2D, texid)

    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR_MIPMAP_LINEAR)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_R, gl.GL_CLAMP_TO_EDGE)

    gl.glTexImage2D(
        gl.GL_TEXTURE_2D,
        0,
        gl.GL_RGBA,
        pixels.shape[0],
        pixels.shape[1],
        0,
        gl.GL_RGBA,
        gl.GL_UNSIGNED_BYTE,
        pixels
    )

    gl.glGenerateMipmap(gl.GL_TEXTURE_2D)

    return texid


def loadCubeMap(fileRight, fileLeft, fileTop, fileBottom, fileFront, fileBack):
    texid = gl.glGenTextures(1)
    gl.glActiveTexture(gl.GL_TEXTURE_CUBE_MAP)
    gl.glBindTexture(gl.GL_TEXTURE_CUBE_MAP, texid)

    gl.glTexParameteri(gl.GL_TEXTURE_CUBE_MAP, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
    gl.glTexParameteri(gl.GL_TEXTURE_CUBE_MAP, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR_MIPMAP_LINEAR)
    gl.glTexParameteri(gl.GL_TEXTURE_CUBE_MAP, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
    gl.glTexParameteri(gl.GL_TEXTURE_CUBE_MAP, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
    gl.glTexParameteri(gl.GL_TEXTURE_CUBE_MAP, gl.GL_TEXTURE_WRAP_R, gl.GL_CLAMP_TO_EDGE)

    files = [
        fileRight,
        fileLeft,
        fileTop,
        fileBottom,
        fileFront,
        fileBack
    ]
    targets = [
        gl.GL_TEXTURE_CUBE_MAP_POSITIVE_X,
        gl.GL_TEXTURE_CUBE_MAP_NEGATIVE_X,
        gl.GL_TEXTURE_CUBE_MAP_POSITIVE_Y,
        gl.GL_TEXTURE_CUBE_MAP_NEGATIVE_Y,
        gl.GL_TEXTURE_CUBE_MAP_POSITIVE_Z,
        gl.GL_TEXTURE_CUBE_MAP_NEGATIVE_Z
    ]

    for filePath, target in zip(files, targets):
        pixels = np.asarray(Image.open(filePath).convert('RGB').resize((256, 256)), dtype=np.uint8)
        gl.glTexImage2D(
            target,
            0,
            gl.GL_RGB,
            pixels.shape[0],
            pixels.shape[1],
            0,
            gl.GL_RGB,
            gl.GL_UNSIGNED_BYTE,
            pixels
        )

    gl.glGenerateMipmap(gl.GL_TEXTURE_CUBE_MAP)

    return texid


ALEMBIC_OPS = {
    '.selfBnds': lambda args: bboxOp(*args),
    'P': lambda args: pointsOp(*args),
    '.faceIndices': lambda args: indicesOp(*args),
    '.faceCounts': lambda args: countsOp(*args),
    # I will calculate smooth normals
    # normal samples didn't work for somne reason
    # 'N': lambda args: normalsOp(*args),
    '.xform': lambda args: xformOp(*args),
    '.core': lambda args: coreOp(*args),
    'uv': {
        '.vals': lambda args: uvValsOp(*args),
        '.indices': lambda args: uvIndicesOp(*args),
    }
    # .filmBackOps
    # .filmBackOps
}


def bboxOp(data, branch):
    branch.bbox = np.array(data, np.float32)


def pointsOp(prop, branch):
    if branch.kind == 'PolyMesh':
        branch.points = np.array(prop.getValues(0), np.float32).reshape(-1, 3)
        branch.pointProp = prop


def indicesOp(data, branch):
    if branch.kind == 'PolyMesh':
        branch.indices = np.array(data, np.uint32)


def countsOp(data, branch):
    if branch.kind == 'PolyMesh':
        branch.counts = np.array(data, np.uint32)


def uvValsOp(data, branch):
    if branch.kind == 'PolyMesh':
        branch.uvs = np.array(data, np.float32).reshape(-1, 2)


def uvIndicesOp(data, branch):
    if branch.kind == 'PolyMesh':
        branch.uvs = branch.uvs[np.array(data, np.uint32)]
        branch.hasUVs = True


def xformOp(data, branch):
    branch.matrix = np.array(data, np.float32).T


def coreOp(data, branch):
    if branch.kind == 'Camera':
        branch.focalLength = data[0]
        branch.horizontalAperture = data[1]
        branch.horizontalFilmOffset = data[2]
        branch.verticalAperture = data[3]
        branch.verticalFilmOffset = data[4]
        branch.lensSqueezeRatio = data[5]
        branch.overscanLeft = data[6]
        branch.overscanRight = data[7]
        branch.overscanTop = data[8]
        branch.overscanBottom = data[9]
        branch.fStop = data[10]
        branch.focusDistance = data[11]
        branch.shutterOpen = data[12]
        branch.shutterClose = data[13]
        branch.nearClippingPlane = data[14]
        branch.farClippingPlane = data[15]


def parseProperties(prop, objPath, objType, branch, compound=None):
    if prop.isCompound():
        propName = prop.getName()
        for subPropName in prop.getPropertyNames():
            parseProperties(
                prop.getProperty(subPropName),
                objPath,
                objType,
                branch,
                compound=propName
            )
    else:
        propName = prop.getName()
        if propName == 'P':
            ALEMBIC_OPS['P'](
                (prop, branch)
            )
        elif propName in ALEMBIC_OPS:
            ALEMBIC_OPS[propName](
                (prop.getValues(0), branch)
            )
        elif compound in ALEMBIC_OPS:
            ALEMBIC_OPS[compound][propName](
                (prop.getValues(0), branch)
            )
        else:
            # print propName
            pass


def rootFromAlembic(filePath):
    archive = alembic.getIArchive(filePath)
    root = Branch('/', rootName=os.path.basename(filePath), isRoot=True)

    sampleTimes = archive.getSampleTimes()
    for timeSample in sampleTimes:
        timeSample.getType()
        timeSample.getTimeSamples()  # obj.getTsIndex()

    for objPath in archive.getIdentifiers():
        obj = archive.getObject(objPath)
        objType = obj.getType()

        branch = None
        if objType.startswith('AbcGeom_PolyMesh'):
            branch = PolyMesh(objPath)
        elif objType.startswith('AbcGeom_Xform'):
            branch = Branch(objPath)
        elif objType.startswith('AbcGeom_Camera'):
            branch = Camera(objPath)
        else:
            # print objType
            continue

        obj.getTsIndex()  # time sampling index
        obj.getMetaData()
        for p in obj.getPropertyNames():
            prop = obj.getProperty(p)
            parseProperties(prop, objPath, objType, branch)

        root.map[objPath] = branch

    return root
