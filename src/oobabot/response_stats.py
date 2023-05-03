import time

from oobabot.ooba_client import OobaClient
from oobabot.fancy_logging import get_logger


class ResponseStats:
    # Purpose: collects timing and rate statistics for responses

    def __init__(self, ooba_client: OobaClient):
        self.ooba_client = ooba_client
        self.requests = 0
        self.responses = 0
        self.errors = 0
        self.total_response_time = 0
        self.total_response_latency = 0
        self.total_tokens = 0
        self.last_response = None

    class ResponseData:
        def __init__(self, ooba_client: OobaClient):
            self.ooba_client = ooba_client
            self.start_time = time.time()
            self.start_tokens = ooba_client.total_response_tokens
            self.duration = 0
            self.latency = 0
            self.tokens = 0

        def log_response_part(self) -> None:
            now = time.time()
            if not self.latency:
                self.latency = now - self.start_time
            self.duration = now - self.start_time
            self.tokens = self.ooba_client.total_response_tokens - \
                self.start_tokens

        def tokens_per_second(self) -> float:
            if not self.duration:
                return 0
            return self.tokens / self.duration

        def write_to_log(self, log_prefix: str) -> None:
            get_logger().debug(
                log_prefix +
                f"tokens: {self.tokens}, " +
                f"time: {self.duration:.2f}s, " +
                f"latency: {self.latency:.2f}s, " +
                f"rate: {self.tokens_per_second():.2f} tok/s")

    def log_request_start(self) -> None:
        self.requests += 1
        self.last_response = self.ResponseData(self.ooba_client)

    def log_response_part(self) -> None:
        if not self.last_response:
            get_logger().error(
                'log_response_part() called without a corresponding ' +
                'log_request_start()'
            )
            return
        self.last_response.log_response_part()

    def log_response_failure(self, error: Exception) -> None:
        self.errors += 1
        get_logger().error(f'Error: {str(error)}')
        self.last_response = None

    def log_response_success(self, log_prefix: str) -> None:
        # make sure this was called at all
        self.log_response_part()
        if not self.last_response:
            get_logger().error(
                'log_response_success() called without a corresponding ' +
                'log_request_start()'
            )
            return

        self.responses += 1
        self.total_response_time += self.last_response.duration
        self.total_response_latency += self.last_response.latency

        self.last_response.write_to_log(log_prefix)
        self.last_response = None

    def write_stat_summary_to_log(self) -> None:
        if 0 == self.requests:
            get_logger().info('No requests handled')
            return

        get_logger().info(
            f'Recevied {self.requests} request(s), ' +
            f'sent {self.responses} successful responses and ' +
            f'had {self.errors} error(s)')

        if (self.errors > 0):
            get_logger().error(
                'Error rate:                  ' +
                f'{self.errors / self.requests * 100:6.2f}%'
            )

        if (self.responses > 0):
            get_logger().debug(
                'Average response time:       ' +
                f'{self.total_response_time / self.responses:6.2f}s'
            )
            get_logger().debug(
                'Average response latency:    ' +
                f'{self.total_response_latency / self.responses:6.2f}s'
            )
            total_tokens = self.ooba_client.total_response_tokens
            get_logger().debug(
                'Average tokens per response: ' +
                f'{total_tokens / self.responses:6.2f}'
            )

        if self.total_response_time > 0:
            tokens_per_second = self.ooba_client.total_response_tokens / \
                self.total_response_time
            get_logger().debug(
                'Average tokens per second:   ' +
                f'{tokens_per_second:6.2f}'
            )
