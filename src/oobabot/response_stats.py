import time

from oobabot.ooba_client import OobaClient
from oobabot.fancy_logging import get_logger


class ResponseStats:
    '''
    Purpose: collects timing and rate statistics for a single response
    '''

    def __init__(self, ooba_client: OobaClient):
        self.ooba_client = ooba_client
        self.start_time = time.time()
        self.start_tokens = ooba_client.total_response_tokens
        self.duration = 0
        self.latency = 0
        self.tokens = 0

    def log_response_part(self) -> None:
        '''
        Call this each time the response is updated by the AI.
        '''

        now = time.time()
        if not self.latency:
            self.latency = now - self.start_time
        self.duration = now - self.start_time
        self.tokens = self.ooba_client.total_response_tokens - \
            self.start_tokens

    def tokens_per_second(self) -> float:
        '''
        Returns the rate at which tokens were generated, in tokens per second.
        '''
        if not self.duration:
            return 0
        return self.tokens / self.duration

    def write_to_log(self, log_prefix: str) -> None:
        '''
        This writes the statistics for this specific
        request to the log.
        '''
        get_logger().debug(
            log_prefix +
            f"tokens: {self.tokens}, " +
            f"time: {self.duration:.2f}s, " +
            f"latency: {self.latency:.2f}s, " +
            f"rate: {self.tokens_per_second():.2f} tok/s")


class AggregateResponseStats:
    '''
    Purpose: collects timing and rate statistics for all AggregateResponseStats
    '''

    def __init__(self, ooba_client: OobaClient):
        self.ooba_client = ooba_client
        self.total_requests_received = 0
        self.total_successful_responses = 0
        self.total_failed_responses = 0
        self.total_response_time_seconds = 0
        self.total_response_latency_seconds = 0

    def log_request_arrived(self) -> ResponseStats:
        '''
        Call this when a request has arrived.
        This must be followed by zero or more calls
        to log_response_part(), and then exactly one call to
        either log_response_failure() or log_response_success().
        '''
        self.total_requests_received += 1
        return ResponseStats(self.ooba_client)

    def log_response_failure(self) -> None:
        '''
        Track the statistics for a failed response.
        '''
        self.total_failed_responses += 1

    def log_response_success(self, response: ResponseStats) -> None:
        '''
        Track the statistics for a successful response, and
        averages them into the overall statistics.

        Parameters:
         - response: the Response object returned
              by log_request_arrived()
        '''
        self.total_successful_responses += 1
        self.total_response_time_seconds += response.duration
        self.total_response_latency_seconds += response.latency

    def error_rate(self) -> float:
        '''
        Returns the percentage of requests that failed.
        '''
        if 0 == self.total_requests_received:
            return 0.0
        return 100 * self.total_failed_responses / self.total_requests_received

    def average_response_time(self) -> float:
        '''
        Returns the average response time in seconds.
        '''
        if 0 == self.total_successful_responses:
            return 0.0
        return self.total_response_time_seconds / \
            self.total_successful_responses

    def average_response_latency(self) -> float:
        '''
        Returns the average response latency in seconds.
        '''
        if 0 == self.total_successful_responses:
            return 0.0
        return self.total_response_latency_seconds / \
            self.total_successful_responses

    def average_tokens_per_second(self) -> float:
        '''
        Returns the average rate at which tokens were generated,
        in tokens per second.
        '''
        if 0 == self.total_successful_responses:
            return 0.0
        return self.ooba_client.total_response_tokens / \
            self.total_response_time_seconds

    def write_stat_summary_to_log(self) -> None:
        '''
        This writes a summary of the statistics to the log.
        Call this after all AggregateResponseStats have been handled.
        '''
        if 0 == self.total_requests_received:
            get_logger().info('No requests handled')
            return

        get_logger().info(
            f'Recevied {self.total_requests_received} request(s), ' +
            f'sent {self.total_successful_responses} successful responses ' +
            f'and failed to send one {self.total_failed_responses} times(s)')

        if (self.total_failed_responses > 0):
            get_logger().error(
                'Error rate:                  ' +
                f'{self.error_rate()}%'
            )

        if (self.total_successful_responses > 0):
            get_logger().debug(
                'Average response time:       ' +
                f'{self.average_response_time():6.2f}s'
            )
            get_logger().debug(
                'Average response latency:    ' +
                f'{self.average_response_latency():6.2f}s'
            )
            get_logger().debug(
                'Average tokens per response: ' +
                f'{self.average_tokens_per_second():6.2f}'
            )

        if self.total_response_time_seconds > 0:
            get_logger().debug(
                'Average tokens per second:   ' +
                f'{self.average_tokens_per_second():6.2f}'
            )
