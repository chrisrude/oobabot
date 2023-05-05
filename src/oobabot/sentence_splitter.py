# Purpose: Split a string into sentences, based on a set of terminators.
#          This is a helper class for ooba_client.py.
import typing

import pysbd


class SentenceSplitter:
    """
    Purpose: Split an English string into sentences.
    """

    # anything that can't be in a real response
    END_OF_INPUT = ""

    def __init__(self):
        self.printed_idx = 0
        self.full_response = ""
        self.segmenter = pysbd.Segmenter(language="en", clean=False, char_span=True)

    def by_sentence(self, new_token: str) -> typing.Generator[str, None, None]:
        """
        Collects tokens into a single string, looks for ends of english
        sentences, then yields each sentence as soon as it's found.

        Parameters:
            new_token: str, the next token to add to the string

        Returns:
            Generator[str, None, None], yields each sentence

        Note:
        When there is no longer any input, the caller must pass
        SentenceSplitter.END_OF_INPUT to this function.  This
        function will then yield any remaining text, even if it
        doesn't look like a full sentence.
        """

        self.full_response += new_token
        unseen = self.full_response[self.printed_idx :]

        # if we've reached the end of input, yield it all,
        # even if we don't think it's a full sentence.
        if self.END_OF_INPUT == new_token:
            to_print = unseen.strip()
            if to_print:
                yield unseen
            self.printed_idx += len(unseen)
            return

        segments = self.segmenter.segment(unseen)

        # any remaining non-sentence things will be in the last element
        # of the list.  Don't print that yet.  At the very worst, we'll
        # print it when the END_OF_INPUT signal is reached.
        for sentence_w_char_spans in segments[:-1]:
            # sentence_w_char_spans is a class with the following fields:
            #  - sent: str, sentence text
            #  - start: start idx of 'sent', relative to original string
            #  - end: end idx of 'sent', relative to original string
            #
            # we want to remove the last '\n' if there is one.
            # we do want to include any other whitespace, though.

            to_print = sentence_w_char_spans.sent  # type: ignore
            if to_print.endswith("\n"):
                to_print = to_print[:-1]

            yield to_print

        # since we've printed all the previous segments,
        # the start of the last segment becomes the starting
        # point for the next roud.
        if len(segments) > 0:
            self.printed_idx += segments[-1].start  # type: ignore
