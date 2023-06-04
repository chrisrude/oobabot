# -*- coding: utf-8 -*-
"""
Purpose: collects timing and rate statistics for the bot's responses
"""

import time
import typing

from oobabot import fancy_logger


class ResponseStats:
    """
    Purpose: collects timing and rate statistics for a single response
    """

    def __init__(self, fn_get_total_tokens: typing.Callable[[], int], prompt: str):
        self.fn_get_total_tokens = fn_get_total_tokens
        self.start_time = time.time()
        self.start_tokens = fn_get_total_tokens()
        self.duration = 0
        self.latency = 0
        self.tokens = 0
        self.prompt_len = len(prompt)

    def log_response_part(self) -> None:
        """
        Call this each time the response is updated by the AI.
        """

        now = time.time()
        if not self.latency:
            self.latency = now - self.start_time
        self.duration = now - self.start_time
        self.tokens = self.fn_get_total_tokens() - self.start_tokens

    def tokens_per_second(self) -> float:
        """
        Returns the rate at which tokens were generated, in tokens per second.
        """
        if not self.duration:
            return 0
        return self.tokens / self.duration

    def write_to_log(self, log_prefix: str) -> None:
        """
        This writes the statistics for this specific
        request to the log.
        """
        fancy_logger.get().debug(
            log_prefix
            + f"tokens: {self.tokens}, "
            + f"time: {self.duration:.2f}s, "
            + f"latency: {self.latency:.2f}s, "
            + f"rate: {self.tokens_per_second():.2f} tok/s"
        )


class AggregateResponseStats:
    """
    Purpose: collects timing and rate statistics for all AggregateResponseStats
    """

    def __init__(self, fn_get_total_tokens: typing.Callable[[], int]):
        self.total_requests_received = 0
        self.total_successful_responses = 0
        self.total_failed_responses = 0
        self.total_response_time_seconds = 0
        self.total_response_latency_seconds = 0
        self.prompt_max_chars = 0
        self.prompt_min_chars = 0
        self.prompt_total_chars = 0
        self.fn_get_total_tokens = fn_get_total_tokens

    def log_request_arrived(self, prompt) -> ResponseStats:
        """
        Call this when a request has arrived.
        This must be followed by zero or more calls
        to log_response_part(), and then exactly one call to
        either log_response_failure() or log_response_success().
        """
        result = ResponseStats(self.fn_get_total_tokens, prompt)

        self.total_requests_received += 1
        # update the prompt stats now
        if self.prompt_max_chars < result.prompt_len:
            self.prompt_max_chars = result.prompt_len
        if self.prompt_min_chars > result.prompt_len:
            self.prompt_min_chars = result.prompt_len
        self.prompt_total_chars += result.prompt_len

        return result

    def log_response_failure(self) -> None:
        """
        Track the statistics for a failed response.
        """
        self.total_failed_responses += 1

    def log_response_success(self, response: ResponseStats) -> None:
        """
        Track the statistics for a successful response, and
        averages them into the overall statistics.

        Parameters:
         - response: the Response object returned
              by log_request_arrived()
        """
        self.total_successful_responses += 1
        self.total_response_time_seconds += response.duration
        self.total_response_latency_seconds += response.latency

    def error_rate(self) -> float:
        """
        Returns the percentage of requests that failed.
        """
        if 0 == self.total_requests_received:
            return 0.0
        return 100 * self.total_failed_responses / self.total_requests_received

    def average_response_time(self) -> float:
        """
        Returns the average response time in seconds.
        """
        if 0 == self.total_successful_responses:
            return 0.0
        return self.total_response_time_seconds / self.total_successful_responses

    def average_response_latency(self) -> float:
        """
        Returns the average response latency in seconds.
        """
        if 0 == self.total_successful_responses:
            return 0.0
        return self.total_response_latency_seconds / self.total_successful_responses

    def average_tokens_per_second(self) -> float:
        """
        Returns the average rate at which tokens were generated,
        in tokens per second.
        """
        if 0 == self.total_successful_responses:
            return 0.0
        if 0.0 == self.total_response_time_seconds:
            return 0.0
        return self.fn_get_total_tokens() / self.total_response_time_seconds

    def average_prompt_length(self) -> float:
        """
        Returns the average prompt length in characters.
        """
        if 0 == self.total_requests_received:
            return 0.0
        return self.prompt_total_chars / self.total_requests_received

    def write_stat_summary_to_log(self) -> None:
        """
        This writes a summary of the statistics to the log.
        Call this after all AggregateResponseStats have been handled.
        """
        if 0 == self.total_requests_received:
            fancy_logger.get().info("No requests handled")
            return

        fancy_logger.get().info(
            f"Received {self.total_requests_received} request(s), "
            + f"sent {self.total_successful_responses} successful responses "
            + f"and failed to send one {self.total_failed_responses} times(s)"
        )

        if self.total_failed_responses > 0:
            fancy_logger.get().error(
                "Error rate:                  %0.2f%%", self.error_rate()
            )

        if self.total_successful_responses > 0:
            fancy_logger.get().debug(
                "Average response time:       %6.2fs", self.average_response_time()
            )
            fancy_logger.get().debug(
                "Average response latency:    %6.2fs", self.average_response_latency()
            )
            fancy_logger.get().debug(
                "Average tokens per response: %6.2f", self.average_tokens_per_second()
            )

        if self.total_response_time_seconds > 0:
            fancy_logger.get().debug(
                "Average tokens per second:   %6.2f", self.average_tokens_per_second()
            )

        fancy_logger.get().debug(
            "Prompt length: "
            + f"max: {self.prompt_max_chars}, "
            + f"min: {self.prompt_min_chars}, "
            + f"avg: {self.average_prompt_length():.2f}"
        )
