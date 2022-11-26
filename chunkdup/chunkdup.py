#!/usr/bin/env python
import signal
import sys
from difflib import SequenceMatcher

from .index import get_index


def diff_ratio(a, b, sizes1, sizes2):
    """
    >>> sizes = {'a': 10, 'b': 10, 'c': 20}
    >>> diff_ratio(['a', 'a', 'a', 'a'], ['a', 'a', 'a', 'a'], sizes, sizes)
    1.0
    >>> diff_ratio(['a', 'a', 'a', 'a'], ['a', 'a', 'b', 'a'], sizes, sizes)
    0.75
    >>> diff_ratio(['a', 'a', 'a', 'a'], ['a', 'c', 'a'], sizes, sizes)
    0.5
    """
    matches = 0
    for tag, i1, i2, _, _ in SequenceMatcher(a=a, b=b).get_opcodes():
        if tag != "equal":
            continue
        matches += sum(
            [sizes1.get(chunk, 0) or sizes2.get(chunk, 0) for chunk in a[i1:i2]],
        )
    size1 = sum([sizes1.get(chunk) for chunk in a])
    size2 = sum([sizes2.get(chunk) for chunk in b])
    ratio = (2 * matches) / (size1 + size2)
    return ratio


def find_dup_files(index1, index2):
    chunks1 = index1.chunk2file_id
    file_ids1 = index1.file_id2chunk
    chunks2 = index2.chunk2file_id
    file_ids2 = index2.file_id2chunk

    same_chunks = set(chunks1) & set(chunks2)

    same_file_ids1 = {c: chunks1[c] for c in same_chunks}
    same_file_ids2 = {c: chunks2[c] for c in same_chunks}

    file_id_pairs = []
    for c in same_chunks:
        ids1 = same_file_ids1[c]
        ids2 = same_file_ids2[c]
        file_id_pairs.extend([(x, y) for x in ids1 for y in ids2])
    file_id_pairs = list(set(file_id_pairs))

    dups = []
    for f1, f2 in file_id_pairs:
        ids1 = file_ids1[f1]
        ids2 = file_ids2[f2]
        path1 = index1._file_ids[f1]
        path2 = index2._file_ids[f2]
        ratio = diff_ratio(ids1, ids2, index1.chunk2size, index2.chunk2size)
        if path1 == path2 and ratio == 1.0:
            continue
        size1 = index1._files[path1]["size"]
        size2 = index2._files[path2]["size"]
        dups.append((ratio, size1, path1, size2, path2))
    return dups


def find_dup(chunksum_file1, chunksum_file2):
    """
    >>> import io
    >>> from pprint import pprint
    >>> chunksum1 = '''
    ... sum1  /A/1  fck0sha2!a:10,b:10
    ... sum2  /A/2  fck0sha2!c:10,d:10,e:10
    ... sum3  /A/3  fck0sha2!f:10,g:10
    ... sum4  /A/4  fck0sha2!h:10
    ... '''
    >>> chunksum2 = '''
    ... sum5  /B/1  fck0sha2!m:10,n:10
    ... sum6  /B/2  fck0sha2!c:10,d:10,f:10
    ... sum7  /B/3  fck0sha2!f:10,x:10
    ... sum8  /B/4  fck0sha2!h:10
    ... '''
    >>> file1 = io.StringIO(chunksum1)
    >>> file2 = io.StringIO(chunksum2)
    >>> pprint(find_dup(file1, file2))
    [(1.0, 10, '/A/4', 10, '/B/4'),
     (0.6666666666666666, 30, '/A/2', 30, '/B/2'),
     (0.5, 20, '/A/3', 20, '/B/3'),
     (0.4, 20, '/A/3', 30, '/B/2')]
    >>> chunksum_repeat = '''
    ... sum  a  fck0sha2!a:1,a:1,a:1,b:2
    ... sum  b  fck0sha2!a:1,b:2
    ... sum  c  fck0sha2!a:1,a:1,a:1,b:2
    ... '''
    >>> file1 = io.StringIO(chunksum_repeat)
    >>> file2 = io.StringIO(chunksum_repeat)
    >>> pprint(find_dup(file1, file2))
    [(1.0, 5, 'c', 5, 'a'),
     (1.0, 5, 'a', 5, 'c'),
     (0.75, 5, 'c', 3, 'b'),
     (0.75, 5, 'a', 3, 'b'),
     (0.75, 3, 'b', 5, 'c'),
     (0.75, 3, 'b', 5, 'a')]
    """
    index1 = get_index(chunksum_file1)
    index2 = get_index(chunksum_file2)
    dups = sorted(find_dup_files(index1, index2), reverse=True)
    return dups


def print_plain_report(dups, output_file):
    """
    >>> import io
    >>> chunksum1 = '''
    ... sum1  /A/1  fck0sha2!a:10,b:10
    ... sum2  /A/2  fck0sha2!c:10,d:10,e:10
    ... sum3  /A/3  fck0sha2!f:10,g:10
    ... sum4  /A/4  fck0sha2!h:10
    ... '''
    >>> chunksum2 = '''
    ... sum5  /B/1  fck0sha2!m:10,n:10
    ... sum6  /B/2  fck0sha2!c:10,d:10,f:10
    ... sum7  /B/3  fck0sha2!f:10,x:10
    ... sum8  /B/4  fck0sha2!h:10
    ... '''
    >>> file1 = io.StringIO(chunksum1)
    >>> file2 = io.StringIO(chunksum2)
    >>> dups = find_dup(file1, file2)
    >>> print_plain_report(dups, sys.stdout)
    100.00%  /A/4 (10B)  /B/4 (10B)
     66.67%  /A/2 (30B)  /B/2 (30B)
     50.00%  /A/3 (20B)  /B/3 (20B)
     40.00%  /A/3 (20B)  /B/2 (30B)

    >>> chunksum_repeat = '''
    ... sum  a  fck0sha2!a:1,a:1,a:1,b:2
    ... sum  b  fck0sha2!a:1,b:2
    ... sum  c  fck0sha2!a:1,a:1,a:1,b:2
    ... '''
    >>> file1 = io.StringIO(chunksum_repeat)
    >>> file2 = io.StringIO(chunksum_repeat)
    >>> dups = find_dup(file1, file2)
    >>> print_plain_report(dups, sys.stdout)
    100.00%  c (5B)  a (5B)
    100.00%  a (5B)  c (5B)
     75.00%  c (5B)  b (3B)
     75.00%  a (5B)  b (3B)
     75.00%  b (3B)  c (5B)
     75.00%  b (3B)  a (5B)
    """
    for ratio, size1, file1, size2, file2 in dups:
        print(
            "{:>6.2f}%  {} ({}B)  {} ({}B)".format(
                ratio * 100,
                file1,
                size1,
                file2,
                size2,
            ),
            file=output_file,
            flush=True,
        )


def help():
    doc = """Find (partial content) duplicate files.

Usage: {cmd} <chunksums_file1> <chunksums_file2>

Examples:

  $ chunksum dir1/ -f chunksums.dir1
  $ chunksum dir2/ -f chunksums.dir2
  $ {cmd} chunksums.dir1 chunksums.dir2
"""

    print(doc.format(cmd=sys.argv[0]))


def main():
    """
    >>> sys.argv = ['chunkdup']
    >>> main()  # doctest: +ELLIPSIS, +NORMALIZE_WHITESPACE
    Find ...
    Usage: ...
    ...

    >>> import tempfile
    >>> f1 = tempfile.NamedTemporaryFile()
    >>> _ = f1.write(b'sum1  /A/1  fck0sha2!a:10,b:10')
    >>> f1.flush()
    >>> f2 = tempfile.NamedTemporaryFile()
    >>> _ = f2.write(b'sum2  /B/1  fck0sha2!c:10,b:10')
    >>> f2.flush()
    >>> sys.argv = ['chunkdup', f1.name, f2.name]
    >>> main()
     50.00%  /A/1 (20B)  /B/1 (20B)
    """

    # Don't turn these signal into exceptions, just die.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    if len(sys.argv) == 3:
        path1, path2 = sys.argv[1:3]
        dups = find_dup(open(path1), open(path2))
        print_plain_report(dups, sys.stdout)
    else:
        help()


if __name__ == "__main__":
    main()  # pragma: no cover
