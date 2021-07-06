""" This is all you need in the lambda"""
from spine_aws_common.mesh import MeshSendMessageChunkApplication

# create instance of class in global space
# this ensures initial setup of logging/config is only done on cold start
app = MeshSendMessageChunkApplication()


def lambda_handler(event, context):
    """Standard lambda_handler"""
    return app.main(event, context)
