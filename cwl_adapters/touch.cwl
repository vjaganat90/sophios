cwlVersion: v1.0

class: CommandLineTool

requirements:
  DockerRequirement:
    dockerPull: docker.io/library/ubuntu:24.04
  InlineJavascriptRequirement: {}

baseCommand: touch

inputs:
  filename:
    type: string
    inputBinding:
      position: 1

outputs:
  file:
    type: File
    outputBinding:
      glob: $(inputs.filename)

