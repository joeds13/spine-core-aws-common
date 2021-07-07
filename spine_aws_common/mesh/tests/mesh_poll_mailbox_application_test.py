""" Testing MeshPollMailbox application """
import json
from unittest import mock, TestCase
import boto3
from moto import mock_s3, mock_ssm, mock_stepfunctions
from spine_aws_common.mesh import MeshPollMailboxApplication
from spine_aws_common.mesh.tests.mesh_testing_common import MeshTestingCommon
from spine_aws_common.tests.utils.log_helper import LogHelper


class TestMeshPollMailboxApplication(TestCase):
    """Testing MeshPollMailbox application"""

    def __init__(self, methodName: str) -> None:
        super().__init__(methodName=methodName)

    @mock_ssm
    @mock_s3
    @mock.patch.dict(
        "os.environ",
        values={
            "AWS_REGION": "eu-west-2",
            "AWS_EXECUTION_ENV": "AWS_Lambda_python3.8",
            "AWS_LAMBDA_FUNCTION_NAME": "lambda_test",
            "AWS_LAMBDA_FUNCTION_MEMORY_SIZE": "128",
            "AWS_LAMBDA_FUNCTION_VERSION": "1",
            "ENV": "meshtest",
            "CHUNK_SIZE": "10",
        },
    )
    def setUp(self):
        """Common setup for all tests"""
        self.log_helper = LogHelper()
        self.log_helper.set_stdout_capture()
        self.maxDiff = 1024  # pylint: disable="invalid-name"
        self.app = MeshPollMailboxApplication()
        self.environment = self.app.system_config["ENV"]

    def tearDown(self) -> None:
        super().tearDown()
        self.log_helper.clean_up()

    @mock_ssm
    @mock_s3
    @mock_stepfunctions
    def test_mesh_poll_mailbox(self):
        """Test the lambda"""
        mailbox_name = "MESH-TEST1"
        mock_input = {"mailbox": mailbox_name}
        s3_client = boto3.client("s3")
        ssm_client = boto3.client("ssm")
        MeshTestingCommon.setup_mock_aws_s3_buckets(self.environment, s3_client)
        MeshTestingCommon.setup_mock_aws_ssm_parameter_store(
            self.environment, ssm_client
        )
        sfn_client = boto3.client("stepfunctions")
        response = MeshTestingCommon.setup_step_function(
            sfn_client,
            self.environment,
            self.app.my_step_function_name,
        )
        try:
            response = self.app.main(
                event=mock_input, context=MeshTestingCommon.CONTEXT
            )
        except Exception as e:  # pylint: disable=broad-except
            # need to fail happy pass on any exception
            self.fail(f"Invocation crashed with Exception {str(e)}")

        print(json.dumps(mock_input))
        print(json.dumps(response))
        self.assertEqual(3, response["body"]["message_count"])
        self.assertLogs("LAMBDA0001", level="INFO")
        self.assertLogs("LAMBDA0002", level="INFO")
        self.assertLogs("LAMBDA0003", level="INFO")