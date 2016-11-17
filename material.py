import OpenGL.GL as gl
from OpenGL.GL import shaders
from PySide import QtCore


class BaseMaterial(QtCore.QObject):
    def __init__(self, vertexShader=None, tessContShader=None, tessEvalShader=None, geometryShader=None, fragmentShader=None):
        super(BaseMaterial, self).__init__()
        self.shaderProg = None
        shaderList = []
        if vertexShader is not None:
            shaderList.append(shaders.compileShader(
                vertexShader,
                gl.GL_VERTEX_SHADER)
            )
        if tessContShader is not None:
            shaderList.append(shaders.compileShader(
                tessContShader,
                gl.GL_TESS_CONTROL_SHADER)
            )
        if tessEvalShader is not None:
            shaderList.append(shaders.compileShader(
                tessEvalShader,
                gl.GL_TESS_EVALUATION_SHADER)
            )
        if geometryShader is not None:
            shaderList.append(shaders.compileShader(
                geometryShader,
                gl.GL_GEOMETRY_SHADER)
            )
        if fragmentShader is not None:
            shaderList.append(shaders.compileShader(
                fragmentShader,
                gl.GL_FRAGMENT_SHADER)
            )
        if len(shaderList) > 0:
            self.shaderProg = shaders.compileProgram(*shaderList)


constantVertCode = '''
#version 450 core
layout(location = 0) in vec3 vert;
uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;
void main() {
    gl_Position = projection * view * model * vec4(vert, 1.);
    gl_PointSize = clamp(gl_Position.z / 100, 3., 5.);
}
'''

constantFragCode = '''
#version 450 core
uniform vec4 inputColor;
out vec4 fragColor;
void main() {
    fragColor = inputColor;
}
'''


class ConstantMaterial(BaseMaterial):
    def __init__(self):
        super(ConstantMaterial, self).__init__(
            vertexShader=constantVertCode,
            fragmentShader=constantFragCode
        )


vertCode = '''
#version 450 core
layout(location = 0) in vec3 vert;

uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;

out vec3 vPosition;

void main()
{
    vPosition = vert;
    gl_Position = projection * view * model * vec4(vPosition, 1.);
}
'''


geometryCode = '''
#version 450 core

layout(triangles) in;
layout(triangle_strip, max_vertices = 3) out;

in vec3 vPosition[];

uniform mat4 model;
uniform mat4 view;

out vec3 gNormal;
out vec3 gPosition;

void main()
{
    vec3 flatNormal = cross(
        vPosition[1] - vPosition[0],
        vPosition[2] - vPosition[0]
    );
    gNormal = normalize(transpose(inverse(mat3(view * model))) * flatNormal);

    gPosition = vPosition[0];
    gl_Position = gl_in[0].gl_Position; EmitVertex();

    gPosition = vPosition[1];
    gl_Position = gl_in[1].gl_Position; EmitVertex();

    gPosition = vPosition[2];
    gl_Position = gl_in[2].gl_Position; EmitVertex();

    EndPrimitive();
}
'''

fragCode = '''
#version 450 core

in vec3 gPosition;
in vec3 gNormal;

uniform mat4 model;
uniform mat4 view;
uniform sampler2D matcap;
uniform vec3 hitPos;
uniform float hitRadius;

out vec4 fragColor;

void main()
{
    vec3 r = reflect(normalize(view * model * vec4(gPosition, 1.)).xyz, gNormal);
    r.y *= -1;
    float m = 2. * sqrt(pow(r.x, 2.) + pow(r.y, 2.) + pow(r.z + 1., 2.));
    vec2 matcapUV = r.xy / m + .5;
    vec3 color = texture2D(matcap, matcapUV.xy).xyz;

    if (distance(gPosition, hitPos) <= hitRadius-.3) {
        color -= (vec3(1.) - color) * .5 + vec3(.1, .5, .6);
    }
    if (distance(gPosition, hitPos) <= hitRadius && distance(gPosition, hitPos) > hitRadius-.3) {
        color -= (vec3(1.) - color) * .3 + vec3(.0, .6, 1.);
    }

    fragColor = vec4(color, 1.);
}
'''


class MatcapMaterial(BaseMaterial):
    def __init__(self):
        super(MatcapMaterial, self).__init__(
            vertexShader=vertCode,
            geometryShader=geometryCode,
            fragmentShader=fragCode
        )
