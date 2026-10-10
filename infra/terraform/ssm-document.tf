resource "aws_ssm_document" "deploy" {
  name            = "RCA-Demo-Deploy"
  document_type   = "Command"
  document_format = "JSON"
  target_type     = "/AWS::EC2::Instance"

  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Deploy digest-pinned RCA Demo frontend and backend images."
    parameters = {
      frontendImage = {
        type              = "String"
        interpolationType = "ENV_VAR"
        allowedPattern    = "^[a-z0-9]+([._-][a-z0-9]+)*/[a-z0-9]+([._-][a-z0-9]+)*@sha256:[0-9a-f]{64}$"
      }
      backendImage = {
        type              = "String"
        interpolationType = "ENV_VAR"
        allowedPattern    = "^[a-z0-9]+([._-][a-z0-9]+)*/[a-z0-9]+([._-][a-z0-9]+)*@sha256:[0-9a-f]{64}$"
      }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "deploy"
      inputs = {
        timeoutSeconds = "900"
        runCommand = [
          "set -eu",
          "/usr/local/bin/rca-demo-deploy \"$SSM_frontendImage\" \"$SSM_backendImage\""
        ]
      }
    }]
  })
}
