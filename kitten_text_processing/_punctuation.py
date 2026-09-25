# Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# Adapted from NeMo 1.2.0 data_loader_utils.py; punctuation helpers only.
import re
import string
import sys
from unicodedata import category
import logging
logger = logging.getLogger(__name__)

def pre_process(text: str) -> str:
    """
    Optional text preprocessing before normalization (part of TTS TN pipeline)

    Args:
        text: string that may include semiotic classes

    Returns: text with spaces around punctuation marks
    """
    space_both = '[]'
    for punct in space_both:
        text = text.replace(punct, ' ' + punct + ' ')

    # remove extra space
    text = re.sub(r' +', ' ', text)
    return text

def post_process_punct(input: str, normalized_text: str, add_unicode_punct: bool = False):
    """
    Post-processing of the normalized output to match input in terms of spaces around punctuation marks.
    After NN normalization, Moses detokenization puts a space after
    punctuation marks, and attaches an opening quote "'" to the word to the right.
    E.g., input to the TN NN model is "12 test' example",
    after normalization and detokenization -> "twelve test 'example" (the quote is considered to be an opening quote,
    but it doesn't match the input and can cause issues during TTS voice generation.)
    The current function will match the punctuation and spaces of the normalized text with the input sequence.
    "12 test' example" -> "twelve test 'example" -> "twelve test' example" (the quote was shifted to match the input).

    Args:
        input: input text (original input to the NN, before normalization or tokenization)
        normalized_text: output text (output of the TN NN model)
        add_unicode_punct: set to True to handle unicode punctuation marks as well as default string.punctuation (increases post processing time)
    """
    # in the post-processing WFST graph "``" are repalced with '"" quotes (otherwise single quotes "`" won't be handled correctly)
    # this function fixes spaces around them based on input sequence, so here we're making the same double quote replacement
    # to make sure these new double quotes work with this function
    if "``" in input and "``" not in normalized_text:
        input = input.replace("``", '"')
    input = [x for x in input]
    normalized_text = [x for x in normalized_text]
    punct_marks = [x for x in string.punctuation if x in input]

    if add_unicode_punct:
        punct_unicode = [
            chr(i)
            for i in range(sys.maxunicode)
            if category(chr(i)).startswith("P") and chr(i) not in punct_marks and chr(i) in input
        ]
        punct_marks = punct_marks.extend(punct_unicode)

    for punct in punct_marks:
        try:
            equal = True
            if input.count(punct) != normalized_text.count(punct):
                equal = False
            idx_in, idx_out = 0, 0
            while punct in input[idx_in:]:
                idx_out = normalized_text.index(punct, idx_out)
                idx_in = input.index(punct, idx_in)

                def _is_valid(idx_out, idx_in, normalized_text, input):
                    """Check if previous or next word match (for cases when punctuation marks are part of
                    semiotic token, i.e. some punctuation can be missing in the normalized text)"""
                    return (idx_out > 0 and idx_in > 0 and normalized_text[idx_out - 1] == input[idx_in - 1]) or (
                        idx_out < len(normalized_text) - 1
                        and idx_in < len(input) - 1
                        and normalized_text[idx_out + 1] == input[idx_in + 1]
                    )

                if not equal and not _is_valid(idx_out, idx_in, normalized_text, input):
                    idx_in += 1
                    continue
                if idx_in > 0 and idx_out > 0:
                    if normalized_text[idx_out - 1] == " " and input[idx_in - 1] != " ":
                        normalized_text[idx_out - 1] = ""

                    elif normalized_text[idx_out - 1] != " " and input[idx_in - 1] == " ":
                        normalized_text[idx_out - 1] += " "

                if idx_in < len(input) - 1 and idx_out < len(normalized_text) - 1:
                    if normalized_text[idx_out + 1] == " " and input[idx_in + 1] != " ":
                        normalized_text[idx_out + 1] = ""
                    elif normalized_text[idx_out + 1] != " " and input[idx_in + 1] == " ":
                        normalized_text[idx_out] = normalized_text[idx_out] + " "
                idx_out += 1
                idx_in += 1
        except:
            logger.info(f"Skipping post-processing of {''.join(normalized_text)} for '{punct}'")

    normalized_text = "".join(normalized_text)
    return re.sub(r' +', ' ', normalized_text)
