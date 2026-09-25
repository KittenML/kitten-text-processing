"""Command-line interface: python -m kitten_text_processing --lang es 'Tengo 2 gatos.'"""
import argparse
import sys
from . import SUPPORTED_LANGUAGES, normalize_text


def main():
    parser = argparse.ArgumentParser(description='Normalize written text for speech; no downloads or dependencies.')
    parser.add_argument('text', nargs='?', help='Text to normalize; otherwise read stdin line by line')
    parser.add_argument('--lang', default='en', help='Language code or locale (' + ', '.join(SUPPORTED_LANGUAGES) + ')')
    args = parser.parse_args()
    try:
        if args.text is not None:
            print(normalize_text(args.text, locale=args.lang))
        else:
            for line in sys.stdin:
                print(normalize_text(line.rstrip('\n'), locale=args.lang))
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
