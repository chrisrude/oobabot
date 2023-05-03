# Purpose: Split a string into sentences, based on a set of terminators.
#          This is a helper class for ooba_client.py.
import pysbd


class SentenceSplitter:

    # anything that can't be in a real response
    END_OF_INPUT = ''

    def __init__(self):
        self.printed_idx = 0
        self.full_response = ''
        self.segmenter = pysbd.Segmenter(
            language="en", clean=False, char_span=True)

    def by_sentence(self, additional_response):
        self.full_response += additional_response
        unseen = self.full_response[self.printed_idx:]

        # if we've reached the end of input, yield it all,
        # even if we don't think it's a full sentence.
        if (self.END_OF_INPUT == additional_response):
            to_print = unseen.strip()
            if (to_print):
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

            to_print = sentence_w_char_spans.sent
            if (to_print.endswith('\n')):
                to_print = to_print[:-1]

            yield to_print

        # since we've printed all the previous segments,
        # the start of the last segment becomes the starting
        # point for the next roud.
        if (len(segments) > 0):
            self.printed_idx += segments[-1].start
