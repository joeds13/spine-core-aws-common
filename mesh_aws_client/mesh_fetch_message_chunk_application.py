"""
Module for MESH API functionality for step functions
"""
from http import HTTPStatus
import os

import boto3

from spine_aws_common import LambdaApplication

from .mesh_common import AwsFailedToPerformError, MeshCommon, MeshMailbox


class MeshFetchMessageChunkApplication(LambdaApplication):
    """
    MESH API Lambda for sending a message
    """

    def __init__(self, additional_log_config=None, load_ssm_params=False):
        """
        Init variables
        """
        super().__init__(additional_log_config, load_ssm_params)
        self.mailbox = None
        self.input = {}
        self.environment = os.environ.get("Environment", "default")
        self.chunk_size = os.environ.get("CHUNK_SIZE", MeshCommon.DEFAULT_CHUNK_SIZE)

    def start(self):
        # TODO refactor
        # pylint: disable=too-many-locals
        self.input = self.event.get("body")
        old_internal_id = self.input.get("internal_id", "Not Provided")
        message_id = self.input["message_id"]
        mailbox_name = self.input["dest_mailbox"]
        self.mailbox = MeshMailbox(self.log_object, mailbox_name, self.environment)
        self.log_object.internal_id = self._create_new_internal_id()
        self.log_object.write_log(
            "MESHFETCH0001",
            None,
            {"original_internal_id": old_internal_id, "message_id": message_id},
        )

        aws_upload_id = self.input.get("aws_upload_id", None)
        chunked = self.input.get("chunked")
        current_chunk = self.input.get("chunk", 1)

        total_chunks = 1
        mailbox_params = self.mailbox.mailbox_params
        bucket = mailbox_params["INBOUND_BUCKET"]
        folder = mailbox_params.get("INBOUND_FOLDER", "")
        if len(folder) > 0:
            folder += "/"

        (return_code, message_object) = self.mailbox.get_chunk(
            message_id, chunk_size=self.chunk_size, chunk_num=1
        )

        s3_client = boto3.client("s3")
        location = {"LocationConstraint": "eu-west-2"}
        filename = message_object.filename
        key = f"{folder}{filename}"

        if current_chunk == 1:
            chunked = return_code == HTTPStatus.PARTIAL_CONTENT.value
            if chunked:
                # create multipart upload
                s3_client.create_multipart_upload(
                    Bucket=bucket,
                    Key=key,
                    CreateBucketConfiguration=location,
                )

        self.response = self.event.raw_event

        # store file to s3 as partial upload or putobject
        if not chunked:
            response = s3_client.put_object(
                Body=message_object.body,
                Bucket=bucket,
                Key=key,
            )
            if (
                response["ResponseMetadata"].get("HTTPStatusCode")
                != HTTPStatus.OK.value
            ):
                self.response.update(
                    {"statusCode": HTTPStatus.INTERNAL_SERVER_ERROR.value}
                )
                self.response["body"].update(
                    {
                        "complete": False,
                        "chunk_num": current_chunk,
                        "aws_upload_id": aws_upload_id,
                        "internal_id": self.log_object.internal_id,
                    }
                )
                # LOGPOINT
                raise AwsFailedToPerformError(
                    f'Failed to put key="{key}" into bucket="{bucket}" '
                    + "to save from MESH"
                )
            # saved successfully, acknowledge message
            self.mailbox.mesh_client.acknowledge_message(message_id)
        else:  # if chunked
            self.response.update({"statusCode": HTTPStatus.NOT_IMPLEMENTED.value})
            self.response["body"].update(
                {
                    "complete": False,
                    "chunk_num": current_chunk,
                    "aws_upload_id": aws_upload_id,
                    "internal_id": self.log_object.internal_id,
                }
            )
            raise NotImplementedError("Chunking not implemented")

        is_finished = current_chunk >= total_chunks if chunked else True
        if chunked:
            if is_finished:
                s3_client.complete_multipart_upload(
                    Bucket=bucket, Key=key, UploadId=aws_upload_id
                )
            else:
                current_chunk += 1

        status_code = HTTPStatus.OK.value
        # update input event to send as response
        self.response.update({"statusCode": status_code})
        self.response["body"].update(
            {
                "complete": is_finished,
                "chunk_num": current_chunk,
                "aws_upload_id": aws_upload_id,
                "internal_id": self.log_object.internal_id,
            }
        )


# create instance of class in global space
# this ensures initial setup of logging/config is only done on cold start
app = MeshFetchMessageChunkApplication()


def lambda_handler(event, context):
    """Standard lambda_handler"""
    return app.main(event, context)
