# pylint: disable=missing-docstring, protected-access
import os
import warnings
import unittest
from unittest.mock import patch  # pylint: disable=unused-import

from pybedtools import create_interval_from_list, BedTool

import iCount  # pylint: disable=unused-import
from iCount.genomes import segment
from iCount.tests.utils import list_to_intervals, intervals_to_list, reverse_strand, make_file_from_list, \
    make_list_from_file, get_temp_file_name, get_temp_dir


class TestConstructBorders(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    def test_basic(self):
        segmentation = [
            # Transcript #1
            ['1', '.', 'ncRNA', '1', '10', '.', '+', '.', 'biotype "A"; gene_name "X";'],
            ['1', '.', 'intron', '11', '20', '.', '+', '.', 'biotype "A"; gene_name "X";'],
            ['1', '.', 'CDS', '21', '30', '.', '+', '.', 'biotype "A"; gene_name "X";'],
            ['1', '.', 'UTR3', '31', '40', '.', '+', '.', 'biotype "A"; gene_name "X";'],
            # Transcript #1
            ['1', '.', 'CDS', '5', '14', '.', '+', '.', 'biotype "A"; gene_name "X";'],
            ['1', '.', 'intron', '15', '24', '.', '+', '.', 'biotype "A"; gene_name "X";'],
            ['1', '.', 'CDS', '25', '34', '.', '+', '.', 'biotype "A"; gene_name "X";'],
            # Also negative strand:
            ['1', '.', 'CDS', '3', '32', '.', '-', '.', 'biotype "A"; gene_name "X";'],
        ]
        expected = [
            ['1', '0', '4', '.', '.', '+'],
            ['1', '4', '10', '.', '.', '+'],
            ['1', '10', '14', '.', '.', '+'],
            ['1', '14', '20', '.', '.', '+'],
            ['1', '20', '24', '.', '.', '+'],
            ['1', '24', '30', '.', '.', '+'],
            ['1', '30', '34', '.', '.', '+'],
            ['1', '34', '40', '.', '.', '+'],
            ['1', '2', '32', '.', '.', '-'],
        ]

        segmentation_file = make_file_from_list(segmentation)
        borders_file = segment.construct_borders(BedTool(segmentation_file))
        results = make_list_from_file(borders_file, fields_separator='\t')
        self.assertEqual(
            expected,
            # Sort results by chrom, strand, start, stop
            sorted(results, key=lambda x: (x[0], x[-1], int(x[1]), int(x[2])))
        )


class TestSimplifyBiotype(unittest.TestCase):

    def test_simplify(self):
        self.assertEqual('mRNA', segment.simplify_biotype('CDS', 'IG_C_gene'))
        self.assertEqual('pre-mRNA', segment.simplify_biotype('intron', 'IG_C_gene'))
        self.assertEqual('lncRNA', segment.simplify_biotype('UTR3', 'TEC'))
        self.assertEqual('lncRNA', segment.simplify_biotype('ncRNA', 'protein_coding'))

    def test_uniqness_of_entries(self):
        """
        Ensure that entries in SUBTYPE_GROUPS do not repeat.
        """
        all_elements = []
        for _, group_elements in segment.SUBTYPE_GROUPS.items():
            all_elements.extend(group_elements)

        self.assertEqual(len(all_elements), len(set(all_elements)))


class TestMakeUniqRegion(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    def test_basic(self):
        # seg is composed of borders(BED6) and segment(GTF) interval:
        seg = create_interval_from_list(
            ['1', '0', '10', '.', '.', '+'] + ['.', '.', '.', '.', '.', '.', '.', '.', '.'])
        types = ['UTR3']
        subtypes = ['TEC']
        genes = [('id1', 'A', 50)]

        interval = segment.make_uniq_region(seg, types, subtypes, genes)
        self.assertEqual(interval[:], ['1', '.', 'UTR3', '1', '10', '.', '+', '.',
                                       'gene_id "id1"; gene_name "A"; biotype "lncRNA";'])

    def test_highest_rated_type(self):
        # seg is compositon of BED6 and GTF interval:
        seg = create_interval_from_list(
            ['1', '0', '10', '.', '.', '+'] + ['.', '.', '.', '.', '.', '.', '.', '.', '.'])
        types = ['UTR3', 'intron', 'UTR5']
        subtypes = ['protein_coding', 'TEC', 'non_stop_decay']
        genes = [('id1', 'A', 20), ('id1', 'A', 20), ('id1', 'A', 20)]

        interval = segment.make_uniq_region(seg, types, subtypes, genes)
        self.assertEqual(interval[:], ['1', '.', 'UTR3', '1', '10', '.', '+', '.',
                                       'gene_id "id1"; gene_name "A"; biotype "mRNA";'])

    def test_multiple_biotypes(self):
        # seg is compositon of BED6 and GTF interval:
        seg = create_interval_from_list(
            ['1', '0', '10', '.', '.', '+'] + ['.', '.', '.', '.', '.', '.', '.', '.', '.'])
        types = ['intron', 'intron']
        subtypes = ['protein_coding', 'TEC']
        genes = [('id1', 'A', 20), ('id1', 'A', 20)]

        interval = segment.make_uniq_region(seg, types, subtypes, genes)
        self.assertEqual(interval[:], ['1', '.', 'intron', '1', '10', '.', '+', '.',
                                       'gene_id "id1"; gene_name "A"; biotype "lncRNA,pre-mRNA";'])

    def test_take_longer_gene(self):
        # seg is compositon of BED6 and GTF interval:
        seg = create_interval_from_list(
            ['1', '0', '10', '.', '.', '+'] + ['.', '.', '.', '.', '.', '.', '.', '.', '.'])
        types = ['CDS', 'CDS']
        subtypes = ['protein_coding', 'protein_coding']
        genes = [('id1', 'A', 20), ('id2', 'B', 40)]

        interval = segment.make_uniq_region(seg, types, subtypes, genes)
        self.assertEqual(interval[:], ['1', '.', 'CDS', '1', '10', '.', '+', '.',
                                       'gene_id "id2"; gene_name "B"; biotype "mRNA";'])

    def test_utr3(self):
        # seg is compositon of BED6 and GTF interval:
        seg = create_interval_from_list(
            ['1', '0', '10', '.', '.', '+'] + ['.', '.', '.', '.', '.', '.', '.', '.', '.'])
        types = ['intron']
        subtypes = ['3prime_overlapping_ncRNA']
        genes = [('id1', 'A', 20)]

        interval = segment.make_uniq_region(seg, types, subtypes, genes)
        self.assertEqual(interval[:], ['1', '.', 'UTR3', '1', '10', '.', '+', '.',
                                       'gene_id "id1"; gene_name "A"; biotype "mRNA";'])

    def test_intergenic(self):
        # seg is compositon of BED6 and GTF interval:
        seg = create_interval_from_list(
            ['1', '0', '10', '.', '.', '+'] + ['.', '.', '.', '.', '.', '.', '.', '.', '.'])
        types = ['intergenic']
        subtypes = [None]
        genes = [('.', None, 0)]

        interval = segment.make_uniq_region(seg, types, subtypes, genes)
        self.assertEqual(interval[:], ['1', '.', 'intergenic', '1', '10', '.', '+', '.',
                                       'gene_id "."; gene_name "None"; biotype "";'])


class TestMergeRegions(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)
        self.tmp = get_temp_file_name()

    def test_basic(self):
        # seg is compositon of BED6 and GTF interval:
        nonmerged = make_file_from_list([
            ['1', '.', 'UTR3', '1', '10', '.', '+', '.', 'biotype "lncRNA";gene_id "id1";'],
            ['1', '.', 'UTR3', '11', '20', '.', '+', '.', 'biotype "lncRNA";gene_id "id1";'],
            ['1', '.', 'UTR3', '21', '30', '.', '+', '.', 'biotype "lncRNA";gene_id "id2";'],
            ['1', '.', 'UTR3', '31', '40', '.', '+', '.', 'biotype "lncRNA";gene_id "id1";'],
            ['1', '.', 'UTR3', '31', '40', '.', '-', '.', 'biotype "lncRNA";gene_id "id1";'],
        ])

        expected = [
            ['1', '.', 'UTR3', '1', '20', '.', '+', '.', 'biotype "lncRNA";gene_id "id1";'],
            ['1', '.', 'UTR3', '21', '30', '.', '+', '.', 'biotype "lncRNA";gene_id "id2";'],
            ['1', '.', 'UTR3', '31', '40', '.', '+', '.', 'biotype "lncRNA";gene_id "id1";'],
            ['1', '.', 'UTR3', '31', '40', '.', '-', '.', 'biotype "lncRNA";gene_id "id1";'],
        ]

        segment.merge_regions(nonmerged, self.tmp)
        results = make_list_from_file(self.tmp, fields_separator='\t')
        # Since order of attrs can be arbitrary, equality checks are more complex:
        for res, exp in zip(results, expected):
            self.assertEqual(res[:8], exp[:8])
            self.assertEqual(
                ';'.join(sorted(res[8].split(';'))),
                ';'.join(sorted(exp[8].split(';'))),
            )


class TestSummaryTemplates(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    def test_templates1(self):
        out_dir = get_temp_dir()
        segmentation = make_file_from_list([
            ['1', '.', 'intergenic', '1', '10', '.', '+', '.', 'gene_id ".";'],
            ['1', '.', 'UTR3', '11', '20', '.', '+', '.', 'biotype "mRNA";gene_name "ABC";gene_id "G1";'],
            ['1', '.', 'intron', '21', '30', '.', '+', '.', 'biotype "lncRNA";gene_name "ABC";gene_id "G1";'],
            ['1', '.', 'CDS', '31', '40', '.', '+', '.', 'biotype "mRNA";gene_name "DEF";gene_id "G2";'],
            ['1', '.', 'intron', '41', '50', '.', '+', '.', 'biotype "sRNA,lncRNA";gene_name "DEF"; gene_id "G2";'],
        ])
        segment.summary_templates(segmentation, out_dir)

        results_type = make_list_from_file(os.path.join(out_dir, segment.TEMPLATE_TYPE), '\t')
        self.assertEqual(results_type, [
            ['CDS', '10'],
            ['UTR3', '10'],
            ['intron', '20'],
            ['intergenic', '10'],
        ])

        results_subtype = make_list_from_file(os.path.join(out_dir, segment.TEMPLATE_SUBTYPE), fields_separator='\t')
        self.assertEqual(results_subtype, [
            ['CDS mRNA', '10'],
            ['UTR3 mRNA', '10'],
            ['intron lncRNA', '15'],
            ['intron sRNA', '5'],
            ['intergenic', '10'],
        ])

        results_gene = make_list_from_file(os.path.join(out_dir, segment.TEMPLATE_GENE), fields_separator='\t')
        self.assertEqual(results_gene, [
            ['.', '', '10'],
            ['G1', 'ABC', '20'],
            ['G2', 'DEF', '20'],
        ])


class TestMakeRegionsFile(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)
        self.dir = get_temp_dir()

    def test_basic(self):
        segmentation = [
            ['1', '.', 'gene', '1', '50', '.', '+', '.', 'biotype "lincRNA"; gene_name "A"; gene_id "X";'],
            # Transcript #1
            ['1', '.', 'transcript', '1', '40', '.', '+', '.', 'biotype "lincRNA"; gene_name "A"; gene_id "X";'],
            ['1', '.', 'ncRNA', '1', '10', '.', '+', '.', 'biotype "lincRNA"; gene_name "A"; gene_id "X";'],
            ['1', '.', 'UTR5', '11', '20', '.', '+', '.', 'biotype "lincRNA"; gene_name "A"; gene_id "X";'],
            ['1', '.', 'CDS', '21', '30', '.', '+', '.', 'biotype "lincRNA"; gene_name "A"; gene_id "X";'],
            ['1', '.', 'intron', '31', '35', '.', '+', '.', 'biotype "lincRNA"; gene_name "A"; gene_id "X";'],
            ['1', '.', 'CDS', '36', '40', '.', '+', '.', 'biotype "lincRNA"; gene_name "A"; gene_id "X";'],
            # Transcript #2
            ['1', '.', 'transcript', '10', '50', '.', '+', '.', 'biotype "rRNA"; gene_name "A"; gene_id "X";'],
            ['1', '.', 'ncRNA', '10', '18', '.', '+', '.', 'biotype "rRNA"; gene_name "A"; gene_id "X";'],
            ['1', '.', 'UTR5', '19', '25', '.', '+', '.', 'biotype "rRNA"; gene_name "A"; gene_id "X";'],
            ['1', '.', 'CDS', '26', '32', '.', '+', '.', 'biotype "rRNA"; gene_name "A"; gene_id "X";'],
            ['1', '.', 'intron', '33', '39', '.', '+', '.', 'biotype "rRNA"; gene_name "A"; gene_id "X";'],
            ['1', '.', 'CDS', '40', '44', '.', '+', '.', 'biotype "rRNA"; gene_name "A"; gene_id "X";'],
            ['1', '.', 'UTR3', '45', '50', '.', '+', '.', 'biotype "rRNA"; gene_name "A"; gene_id "X";'],
            # Itergenic
            ['1', '.', 'intergenic', '51', '100', '.', '+', '.', 'gene_id ".";'],

        ]
        expected = [
            ['1', '.', 'ncRNA', '1', '9', '.', '+', '.', 'gene_id "X";biotype "lncRNA";gene_name "A";'],
            ['1', '.', 'ncRNA', '10', '10', '.', '+', '.', 'gene_id "X";biotype "lncRNA,rRNA";gene_name "A";'],
            ['1', '.', 'UTR5', '11', '18', '.', '+', '.', 'gene_id "X";biotype "lncRNA";gene_name "A";'],
            ['1', '.', 'UTR5', '19', '20', '.', '+', '.', 'gene_id "X";biotype "lncRNA,rRNA";gene_name "A";'],
            ['1', '.', 'CDS', '21', '25', '.', '+', '.', 'gene_id "X";biotype "lncRNA";gene_name "A";'],
            ['1', '.', 'CDS', '26', '30', '.', '+', '.', 'gene_id "X";biotype "lncRNA,rRNA";gene_name "A";'],
            ['1', '.', 'CDS', '31', '32', '.', '+', '.', 'gene_id "X";biotype "rRNA";gene_name "A";'],
            ['1', '.', 'intron', '33', '35', '.', '+', '.', 'gene_id "X";biotype "lncRNA,rRNA";gene_name "A";'],
            ['1', '.', 'CDS', '36', '39', '.', '+', '.', 'gene_id "X";biotype "lncRNA";gene_name "A";'],
            ['1', '.', 'CDS', '40', '40', '.', '+', '.', 'gene_id "X";biotype "lncRNA,rRNA";gene_name "A";'],
            ['1', '.', 'CDS', '41', '44', '.', '+', '.', 'gene_id "X";biotype "rRNA";gene_name "A";'],
            ['1', '.', 'UTR3', '45', '50', '.', '+', '.', 'gene_id "X";biotype "rRNA";gene_name "A";'],
            ['1', '.', 'intergenic', '51', '100', '.', '+', '.', 'gene_id ".";biotype "";gene_name "None";'],
        ]

        segmentation_file = make_file_from_list(segmentation, sort=True)
        segment.make_regions(segmentation_file, self.dir)
        results = make_list_from_file(os.path.join(self.dir, segment.REGIONS_FILE), fields_separator='\t')

        # Since order of attrs can be arbitrary, equality checks are more complex:
        for res, exp in zip(results, expected):
            self.assertEqual(res[:8], exp[:8])
            self.assertEqual(
                ';'.join(sorted(res[8].split(';'))),
                ';'.join(sorted(exp[8].split(';'))),
            )


class TestOtherFunctions(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    def test_a_in_b(self):
        second = create_interval_from_list(['1', '10', '20', 'Name', '42', '+'])

        # a completely in b
        first = create_interval_from_list(['1', '12', '18', 'Name', '42', '+'])
        self.assertTrue(segment._a_in_b(first, second))

        # a == b
        first = create_interval_from_list(['1', '10', '20', 'Name', '42', '+'])
        self.assertTrue(segment._a_in_b(first, second))

        # a streches out of b on left
        first = create_interval_from_list(['1', '5', '15', 'Name', '42', '+'])
        self.assertFalse(segment._a_in_b(first, second))

        # a streches out of b on right
        first = create_interval_from_list(['1', '15', '25', 'Name', '42', '+'])
        self.assertFalse(segment._a_in_b(first, second))

        # a completely out of b
        first = create_interval_from_list(['1', '25', '35', 'Name', '42', '+'])
        self.assertFalse(segment._a_in_b(first, second))

    def test_get_biotype(self):
        transcript_ensembl = create_interval_from_list(
            ['1', '.', 'gene', '1', '200', '.', '+', '.', 'transcript_biotype "T";'])
        transcript_gencode = create_interval_from_list(
            ['1', '.', 'gene', '1', '200', '.', '+', '.', 'transcript_type "T";'])
        self.assertEqual(segment._get_biotype(transcript_ensembl), 'T')
        self.assertEqual(segment._get_biotype(transcript_gencode), 'T')

        gene_ensembl = create_interval_from_list(
            ['1', '.', 'gene', '1', '200', '.', '+', '.', 'gene_biotype "G";'])
        gene_gencode = create_interval_from_list(
            ['1', '.', 'gene', '1', '200', '.', '+', '.', 'gene_type "G";'])
        self.assertEqual(segment._get_biotype(gene_ensembl), 'G')
        self.assertEqual(segment._get_biotype(gene_gencode), 'G')

        gene_ensembl_old = create_interval_from_list(
            ['1', 'Q', 'gene', '1', '200', '.', '+', '.', 'gene_id "1";'])
        self.assertEqual(segment._get_biotype(gene_ensembl_old), 'Q')

    def test_add_biotype_value(self):
        interval = create_interval_from_list(['1', '.', 'gene', '1', '200', '.', '+', '.', 'gene_id "1";'])
        interval_new = segment._add_biotype_value(interval, 'my_biotype')
        self.assertEqual(interval_new.attrs['biotype'], 'my_biotype')

    def test_add_biotype_attribute1(self):
        gene_content = {
            'gene': create_interval_from_list(
                ['1', '.', 'gene', '1', '200', '.', '+', '.', 'gene_biotype "G";']
            ),
            'transcript1': list_to_intervals([
                ['1', '.', 'CDS', '1', '5', '.', '+', '.', 'gene_biotype "G"; transcript_biotype "A";'],
                ['1', '.', 'ncRNA', '1', '5', '.', '+', '.', 'gene_biotype "G"; transcript_biotype "A";'],
                ['1', '.', 'intron', '1', '5', '.', '+', '.', '.'],
            ]),
            'transcript2': list_to_intervals([
                ['1', '.', 'ncRNA', '1', '5', '.', '+', '.', 'gene_biotype "G"; transcript_biotype "B";'],
                ['1', '.', 'intron', '1', '5', '.', '+', '.', '.'],
            ]),
        }

        out = segment._add_biotype_attribute(gene_content)

        for transcript_id, tr_intervals in sorted(out.items()):
            if transcript_id == 'gene':
                # I this case tjhi is single interval not a list of intervals:
                self.assertEqual(tr_intervals.attrs['biotype'], 'A, B, G')
            elif transcript_id == 'transcript1':
                for interval in tr_intervals:
                    self.assertEqual(interval.attrs['biotype'], 'A')
            elif transcript_id == 'transcript2':
                for interval in tr_intervals:
                    self.assertEqual(interval.attrs['biotype'], 'B')

    def test_check_consistency_pass(self):  # pylint: disable=no-self-use
        intervals = list_to_intervals([
            ['1', '.', 'transcript', '1', '100', '.', '+', '.', '.'],
            ['1', '.', 'UTR5', '1', '9', '.', '+', '.', '.'],
            ['1', '.', 'CDS', '10', '49', '.', '+', '.', '.'],
            ['1', '.', 'intron', '50', '59', '.', '+', '.', '.'],
            ['1', '.', 'CDS', '60', '89', '.', '+', '.', '.'],
            ['1', '.', 'UTR3', '90', '100', '.', '+', '.', '.'],

        ])

        # If no AssertionError is raised, this is succes:
        segment._check_consistency(intervals)

    def test_check_consistency_fail1(self):
        """
        No transcript interval.
        """
        intervals = [create_interval_from_list(['1', '.', 'UTR5', '1', '9', '.', '+', '.', '.'])]

        message = "No transcript interval in list of intervals."
        with self.assertRaisesRegex(ValueError, message):
            segment._check_consistency(intervals)

    def test_check_consistency_fail2(self):
        """
        Overlaping intervals.
        """
        intervals = list_to_intervals([
            ['1', '.', 'transcript', '1', '100', '.', '+', '.', '.'],
            ['1', '.', 'UTR5', '1', '50', '.', '+', '.', '.'],
            ['1', '.', 'CDS', '50', '100', '.', '+', '.', '.'],
        ])

        with self.assertRaises(AssertionError):
            segment._check_consistency(intervals)

    def test_check_consistency_fail3(self):
        """
        Unallowed order of types.
        """
        intervals = list_to_intervals([
            ['1', '.', 'transcript', '1', '100', '.', '+', '.', '.'],
            ['1', '.', 'UTR3', '1', '49', '.', '+', '.', '.'],
            ['1', '.', 'CDS', '50', '100', '.', '+', '.', '.'],
        ])

        with self.assertRaises(AssertionError):
            segment._check_consistency(intervals)

    def test_filter_col8(self):
        interval = list_to_intervals([
            ['1', '.', 'CDS', '1', '2', '.', '+', '.', 'gene_name "B"; transcript_id "A"; key42 "A"; key43: "?";'],
        ])[0]

        expected = 'gene_name "B"; transcript_id "A";'
        self.assertEqual(segment._filter_col8(interval), expected)

        expected = 'gene_name "B"; key42 "A";'
        self.assertEqual(segment._filter_col8(interval, keys=['gene_name', 'key42']), expected)

    def test_get_introns(self):
        exons = list_to_intervals([
            ['1', '.', 'exon', '1', '10', '.', '+', '.', 'transcript_id "42"; exon_number "1"'],
            ['1', '.', 'exon', '20', '30', '.', '+', '.', 'gene_name "42"; '],
            ['1', '.', 'exon', '40', '50', '.', '+', '.', 'gene_id "FHIT"; useless_data "3"'],
        ])

        expected = list_to_intervals([
            ['1', '.', 'exon', '11', '19', '.', '+', '.', 'transcript_id "42";'],
            ['1', '.', 'exon', '31', '39', '.', '+', '.', 'gene_id "FHIT";'],
        ])
        self.assertEqual(segment._get_introns(exons), expected)


class TestGetNonCdsExons(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    def test_1(self):
        """
        Situation:
            * no stop codons
            * 1 "empty" exon before first cds
            * 1 "empty" exon after last cds
            * 1 exons shared by UTR5 and CDS
            * 1 exons shared by UTR3 and CDS
        """
        intervals = list_to_intervals([
            # for this test no more than one interval is needed...
            ['1', '.', 'transcript', '20', '90', '.', '+', '.', '.'],
        ])
        exons = list_to_intervals([
            ['1', '.', 'exon', '20', '30', '.', '+', '.', '.'],
            ['1', '.', 'exon', '40', '50', '.', '+', '.', '.'],
            ['1', '.', 'exon', '60', '70', '.', '+', '.', '.'],
            ['1', '.', 'exon', '80', '90', '.', '+', '.', '.'],
        ])
        cdses = list_to_intervals([
            ['1', '.', 'CDS', '45', '50', '.', '+', '.', '.'],
            ['1', '.', 'CDS', '60', '65', '.', '+', '.', '.'],
        ])

        expeted_new_cdses = [
            ['1', '.', 'CDS', '45', '50', '.', '+', '.', '.'],
            ['1', '.', 'CDS', '60', '65', '.', '+', '.', '.'],
        ]
        expeted_utrs = [
            ['1', '.', 'UTR5', '20', '30', '.', '+', '.', '.'],
            ['1', '.', 'UTR5', '40', '44', '.', '+', '.', '.'],
            ['1', '.', 'UTR3', '66', '70', '.', '+', '.', '.'],
            ['1', '.', 'UTR3', '80', '90', '.', '+', '.', '.'],
        ]
        new_cdses, utrs = segment._get_non_cds_exons(cdses, exons, intervals)
        new_cdses, utrs = intervals_to_list(new_cdses), intervals_to_list(utrs)
        self.assertEqual(expeted_new_cdses, new_cdses)
        self.assertEqual(expeted_utrs, utrs)

        # Also test for negative strand:
        intervals, exons, cdses = map(reverse_strand, [intervals, exons, cdses])

        expeted_new_cdses = reverse_strand(expeted_new_cdses)
        expeted_utrs = [
            ['1', '.', 'UTR3', '20', '30', '.', '-', '.', '.'],
            ['1', '.', 'UTR3', '40', '44', '.', '-', '.', '.'],
            ['1', '.', 'UTR5', '66', '70', '.', '-', '.', '.'],
            ['1', '.', 'UTR5', '80', '90', '.', '-', '.', '.'],
        ]

        new_cdses, utrs = segment._get_non_cds_exons(cdses, exons, intervals)
        new_cdses, utrs = intervals_to_list(new_cdses), intervals_to_list(utrs)
        self.assertEqual(expeted_new_cdses, new_cdses)
        self.assertEqual(expeted_utrs, utrs)

    def test_merging_stop_codons_1(self):
        """
        Situation:
            * stop codon and CDS completely overlap
        """
        intervals = list_to_intervals([
            # for this test no more than is needed...
            ['1', '.', 'transcript', '20', '62', '.', '+', '.', '.'],
            ['1', '.', 'stop_codon', '60', '62', '.', '+', '.', '.'],
        ])
        exons = list_to_intervals([
            ['1', '.', 'exon', '20', '40', '.', '+', '.', '.'],
            ['1', '.', 'exon', '60', '62', '.', '+', '.', '.'],
        ])
        cdses = list_to_intervals([
            ['1', '.', 'CDS', '20', '40', '.', '+', '.', '.'],
            ['1', '.', 'CDS', '60', '62', '.', '+', '.', '.'],
        ])

        expeted_new_cdses = [
            ['1', '.', 'CDS', '20', '40', '.', '+', '.', '.'],
            ['1', '.', 'CDS', '60', '62', '.', '+', '.', '.'],
        ]
        expeted_utrs = []
        new_cdses, utrs = segment._get_non_cds_exons(cdses, exons, intervals)
        new_cdses, utrs = intervals_to_list(new_cdses), intervals_to_list(utrs)
        self.assertEqual(expeted_new_cdses, new_cdses)
        self.assertEqual(expeted_utrs, utrs)

        # Negative strand:
        intervals = list_to_intervals([
            # for this test no more than is needed...
            ['1', '.', 'transcript', '20', '80', '.', '-', '.', '.'],
            ['1', '.', 'stop_codon', '20', '22', '.', '-', '.', '.'],
        ])
        exons = list_to_intervals([
            ['1', '.', 'exon', '20', '22', '.', '+', '.', '.'],
            ['1', '.', 'exon', '60', '80', '.', '+', '.', '.'],
        ])
        cdses = list_to_intervals([
            ['1', '.', 'CDS', '20', '22', '.', '-', '.', '.'],
            ['1', '.', 'CDS', '60', '80', '.', '-', '.', '.'],
        ])

        expeted_new_cdses = [
            ['1', '.', 'CDS', '20', '22', '.', '-', '.', '.'],
            ['1', '.', 'CDS', '60', '80', '.', '-', '.', '.'],
        ]
        expeted_utrs = []
        new_cdses, utrs = segment._get_non_cds_exons(cdses, exons, intervals)
        new_cdses, utrs = intervals_to_list(new_cdses), intervals_to_list(utrs)
        self.assertEqual(expeted_new_cdses, new_cdses)
        self.assertEqual(expeted_utrs, utrs)

    def test_merging_stop_codons_2(self):
        """
        Situation:
            * 1 stop codon given on same exon as CDS
        """
        intervals = list_to_intervals([
            # for this test no more than one interval is needed...
            ['1', '.', 'transcript', '60', '70', '.', '+', '.', '.'],
            ['1', '.', 'stop_codon', '63', '65', '.', '+', '.', '.'],
        ])
        exons = list_to_intervals([
            ['1', '.', 'exon', '60', '70', '.', '+', '.', '.'],
        ])
        cdses = list_to_intervals([
            ['1', '.', 'CDS', '60', '62', '.', '+', '.', '.'],
        ])

        expeted_new_cdses = [
            ['1', '.', 'CDS', '60', '65', '.', '+', '.', '.'],
        ]
        expeted_utrs = [
            ['1', '.', 'UTR3', '66', '70', '.', '+', '.', '.'],
        ]
        new_cdses, utrs = segment._get_non_cds_exons(cdses, exons, intervals)
        new_cdses, utrs = intervals_to_list(new_cdses), intervals_to_list(utrs)
        self.assertEqual(expeted_new_cdses, new_cdses)
        self.assertEqual(expeted_utrs, utrs)

        # Negative strand:
        intervals = list_to_intervals([
            # for this test no more than one interval is needed...
            ['1', '.', 'transcript', '60', '70', '.', '-', '.', '.'],
            ['1', '.', 'stop_codon', '63', '65', '.', '-', '.', '.'],
        ])
        exons = list_to_intervals([
            ['1', '.', 'exon', '60', '70', '.', '-', '.', '.'],
        ])
        cdses = list_to_intervals([
            ['1', '.', 'CDS', '66', '70', '.', '-', '.', '.'],
        ])

        expeted_new_cdses = [
            ['1', '.', 'CDS', '63', '70', '.', '-', '.', '.'],
        ]
        expeted_utrs = [
            ['1', '.', 'UTR3', '60', '62', '.', '-', '.', '.'],
        ]
        new_cdses, utrs = segment._get_non_cds_exons(cdses, exons, intervals)
        new_cdses, utrs = intervals_to_list(new_cdses), intervals_to_list(utrs)
        self.assertEqual(expeted_new_cdses, new_cdses)
        self.assertEqual(expeted_utrs, utrs)

    def test_merging_stop_codons_3(self):
        """
        Situation:
            * 1 stop codon given on same exon as CDS, bit inside CDS!
        """
        intervals = list_to_intervals([
            # for this test no more than one interval is needed...
            ['1', '.', 'transcript', '60', '70', '.', '+', '.', '.'],
            ['1', '.', 'stop_codon', '63', '65', '.', '+', '.', '.'],
        ])
        exons = list_to_intervals([
            ['1', '.', 'exon', '60', '70', '.', '+', '.', '.'],
        ])
        cdses = list_to_intervals([
            ['1', '.', 'CDS', '60', '65', '.', '+', '.', '.'],
        ])

        expeted_new_cdses = [
            ['1', '.', 'CDS', '60', '65', '.', '+', '.', '.'],
        ]
        expeted_utrs = [
            ['1', '.', 'UTR3', '66', '70', '.', '+', '.', '.'],
        ]
        new_cdses, utrs = segment._get_non_cds_exons(cdses, exons, intervals)
        new_cdses, utrs = intervals_to_list(new_cdses), intervals_to_list(utrs)
        self.assertEqual(expeted_new_cdses, new_cdses)
        self.assertEqual(expeted_utrs, utrs)

        # Negative strand:
        intervals = list_to_intervals([
            # for this test no more than one interval is needed...
            ['1', '.', 'transcript', '60', '70', '.', '-', '.', '.'],
            ['1', '.', 'stop_codon', '65', '67', '.', '-', '.', '.'],
        ])
        exons = list_to_intervals([
            ['1', '.', 'exon', '60', '70', '.', '-', '.', '.'],
        ])
        cdses = list_to_intervals([
            ['1', '.', 'CDS', '65', '70', '.', '-', '.', '.'],
        ])

        expeted_new_cdses = [
            ['1', '.', 'CDS', '65', '70', '.', '-', '.', '.'],
        ]
        expeted_utrs = [
            ['1', '.', 'UTR3', '60', '64', '.', '-', '.', '.'],
        ]
        new_cdses, utrs = segment._get_non_cds_exons(cdses, exons, intervals)
        new_cdses, utrs = intervals_to_list(new_cdses), intervals_to_list(utrs)
        self.assertEqual(expeted_new_cdses, new_cdses)
        self.assertEqual(expeted_utrs, utrs)

    def test_merging_stop_codons_4(self):
        """
        Situation:
            * 1 stop codon split in two exons
        """
        intervals = list_to_intervals([
            # for this test no more than one interval is needed...
            ['1', '.', 'transcript', '20', '70', '.', '+', '.', '.'],
            ['1', '.', 'stop_codon', '40', '40', '.', '+', '.', '.'],
            ['1', '.', 'stop_codon', '60', '61', '.', '+', '.', '.'],
        ])
        exons = list_to_intervals([
            ['1', '.', 'exon', '20', '40', '.', '+', '.', '.'],
            ['1', '.', 'exon', '60', '70', '.', '+', '.', '.'],
        ])
        cdses = list_to_intervals([
            ['1', '.', 'CDS', '30', '39', '.', '+', '.', '.'],
        ])

        expeted_new_cdses = [
            ['1', '.', 'CDS', '30', '40', '.', '+', '.', '.'],
            ['1', '.', 'CDS', '60', '61', '.', '+', '.', '.'],
        ]
        expeted_utrs = [
            ['1', '.', 'UTR5', '20', '29', '.', '+', '.', '.'],
            ['1', '.', 'UTR3', '62', '70', '.', '+', '.', '.'],
        ]
        new_cdses, utrs = segment._get_non_cds_exons(cdses, exons, intervals)
        new_cdses, utrs = intervals_to_list(new_cdses), intervals_to_list(utrs)
        self.assertEqual(expeted_new_cdses, new_cdses)
        self.assertEqual(expeted_utrs, utrs)

        # Negative strand:
        intervals = list_to_intervals([
            # for this test no more than one interval is needed...
            ['1', '.', 'transcript', '20', '80', '.', '-', '.', '.'],
            ['1', '.', 'stop_codon', '39', '40', '.', '-', '.', '.'],
            ['1', '.', 'stop_codon', '60', '60', '.', '-', '.', '.'],
        ])
        exons = list_to_intervals([
            ['1', '.', 'exon', '20', '40', '.', '-', '.', '.'],
            ['1', '.', 'exon', '60', '80', '.', '-', '.', '.'],
        ])
        cdses = list_to_intervals([
            ['1', '.', 'CDS', '61', '65', '.', '-', '.', '.'],
        ])

        expeted_new_cdses = [
            ['1', '.', 'CDS', '60', '65', '.', '-', '.', '.'],
            ['1', '.', 'CDS', '39', '40', '.', '-', '.', '.'],
        ]
        expeted_utrs = [
            ['1', '.', 'UTR3', '20', '38', '.', '-', '.', '.'],
            ['1', '.', 'UTR5', '66', '80', '.', '-', '.', '.'],
        ]
        new_cdses, utrs = segment._get_non_cds_exons(cdses, exons, intervals)
        new_cdses, utrs = intervals_to_list(new_cdses), intervals_to_list(utrs)
        self.assertEqual(expeted_new_cdses, new_cdses)
        self.assertEqual(expeted_utrs, utrs)


class TestProcessTranscriptGroup(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    def test_no_exons(self):
        """
        Fail if no exons are given.
        """
        intervals = list_to_intervals([
            ['1', '.', 'transcript', '1', '100', '.', '+', '.', '.'],
        ])

        with self.assertRaises(AssertionError):
            segment._process_transcript_group(intervals)

    def test_no_transcript_interval(self):
        """
        If not transcript interval is given, it is determined by function
        Also this is the case if no CDS are given - all exons turn to ncRNA.
        """
        intervals = list_to_intervals([
            ['1', '.', 'exon', '1', '30', '.', '+', '.', 'exon_number "1";'],
            ['1', '.', 'exon', '60', '100', '.', '+', '.', 'exon_number "2";'],
        ])

        expected = [
            ['1', '.', 'transcript', '1', '100', '.', '+', '.', ''],
            ['1', '.', 'intron', '31', '59', '.', '+', '.', ''],
            ['1', '.', 'ncRNA', '1', '30', '.', '+', '.', 'exon_number "1";'],
            ['1', '.', 'ncRNA', '60', '100', '.', '+', '.', 'exon_number "2";'],
        ]

        output = intervals_to_list(segment._process_transcript_group(intervals))
        self.assertEqual(output, expected)

    @unittest.mock.patch('builtins.print')
    def test_fail_validating(self, print_mock):
        """
        Fail on validation.

        Mock the print function to suppress the actual printing during test.
        """
        intervals = list_to_intervals([
            ['1', '.', 'transcript', '1', '200', '.', '+', '.', 'transcript_id "42";'],
            ['1', '.', 'exon', '1', '30', '.', '+', '.', 'exon_number "1";'],
            ['1', '.', 'exon', '60', '100', '.', '+', '.', 'exon_number "2";'],
        ])

        with self.assertRaises(AssertionError):
            segment._process_transcript_group(intervals)
        self.assertEqual(print_mock.call_count, 8)


class TestComplement(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    def test_complement(self):

        genome_file = make_file_from_list(
            [
                ['1', '2000'],
                ['2', '1000'],
                ['MT', '500'],
            ], bedtool=False)

        genes = list_to_intervals([
            ['1', '.', 'gene1', '200', '400', '.', '+', '.', '.'],
            ['1', '.', 'gene2', '300', '600', '.', '+', '.', '.'],
            ['1', '.', 'gene3', '200', '500', '.', '+', '.', '.'],
            ['2', '.', 'gene4', '100', '200', '.', '+', '.', '.'],
            ['2', '.', 'gene5', '100', '300', '.', '-', '.', '.'],
        ])

        complement = make_list_from_file(segment._complement(genes, genome_file, '+'), fields_separator='\t')

        empty_col8 = 'ID "inter%s"; gene_id "."; transcript_id ".";'
        expected = [
            ['1', '.', 'intergenic', '1', '199', '.', '+', '.', empty_col8 % "P00000"],
            ['1', '.', 'intergenic', '601', '2000', '.', '+', '.', empty_col8 % "P00001"],
            ['2', '.', 'intergenic', '1', '99', '.', '+', '.', empty_col8 % "P00002"],
            ['2', '.', 'intergenic', '201', '1000', '.', '+', '.', empty_col8 % "P00003"],
            ['MT', '.', 'intergenic', '1', '500', '.', '+', '.', empty_col8 % "P00004"],
        ]

        self.assertEqual(complement, expected)


class TestGetGeneContent(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    def test_all_good(self):
        """
        * second gene has no 'gene' interval - but it is present in output as it should
        * last interval is on chromosome 2, but it is not in the output
        """
        gtf_data = list_to_intervals([
            ['1', '.', 'gene', '100', '300', '.', '+', '.', 'gene_id "G1";'],
            ['1', '.', 'transcript', '100', '250', '.', '+', '.', 'gene_id "G1"; transcript_id "T1";'],
            ['1', '.', 'exon', '100', '150', '.', '+', '.', 'gene_id "G1"; transcript_id "T1"; exon_number "1";'],
            ['1', '.', 'exon', '200', '250', '.', '+', '.', 'gene_id "G1"; transcript_id "T1"; exon_number "2";'],
            ['1', '.', 'transcript', '150', '300', '.', '+', '.', 'gene_id "G1"; transcript_id "T2";'],
            ['1', '.', 'exon', '150', '200', '.', '+', '.', 'gene_id "G1"; transcript_id "T2"; exon_number "1";'],
            ['1', '.', 'exon', '250', '300', '.', '+', '.', 'gene_id "G1"; transcript_id "T2"; exon_number "2";'],
            ['1', '.', 'transcript', '400', '500', '.', '+', '.', 'gene_id "G2"; transcript_id "T3";'],
            ['1', '.', 'exon', '400', '430', '.', '+', '.', 'gene_id "G2"; transcript_id "T3"; exon_number "1"'],
            ['1', '.', 'CDS', '410', '430', '.', '+', '.', 'gene_id "G2"; transcript_id "T3";'],
            ['1', '.', 'exon', '470', '500', '.', '+', '.', 'gene_id "G2"; transcript_id "T3"; exon_number "2"'],
            ['1', '.', 'CDS', '470', '490', '.', '+', '.', 'gene_id "G2"; transcript_id "T3";'],
            ['2', '.', 'CDS', '470', '490', '.', '+', '.', 'gene_id "G3"; transcript_id "T4";'],
        ])
        gtf = make_file_from_list(intervals_to_list(gtf_data))

        gene1, gene2 = list(segment._get_gene_content(gtf, ['1', 'MT'], report_progress=True))

        expected1 = {
            'gene': gtf_data[0],
            'T1': gtf_data[1:4],
            'T2': gtf_data[4:7],
        }

        extra_gene = create_interval_from_list(['1', '.', 'gene', '400', '500', '.', '+', '.', 'gene_id "G2";'])
        expected2 = {
            'gene': extra_gene,
            'T3': gtf_data[7:-1],
        }

        self.assertEqual(gene1, expected1)
        self.assertEqual(gene2, expected2)

    def test_already_processed(self):
        """
        Raise error if member of already processed transcript is found.
        """
        gtf = make_file_from_list([
            ['1', '.', 'gene', '100', '300', '.', '+', '.', 'gene_id "G1";'],
            ['1', '.', 'transcript', '100', '250', '.', '+', '.', 'gene_id "G1"; transcript_id "T1";'],
            ['1', '.', 'transcript', '150', '300', '.', '+', '.', 'gene_id "G1"; transcript_id "T2";'],
            ['1', '.', 'exon', '150', '200', '.', '+', '.', 'gene_id "G1"; transcript_id "T1"; exon_number "1";'],
        ])

        with self.assertRaises(AssertionError):
            next((segment._get_gene_content(gtf, ['1', 'MT'])))

    def test_already_processed_gene(self):
        """
        Raise error if member of already processed gene is found.
        """
        gtf = make_file_from_list([
            ['1', '.', 'gene', '100', '300', '.', '+', '.', 'gene_id "G1";'],
            ['1', '.', 'transcript', '100', '250', '.', '+', '.', 'gene_id "G1"; transcript_id "T1";'],
            ['1', '.', 'gene', '500', '700', '.', '+', '.', 'gene_id "G2";'],
            ['1', '.', 'transcript', '500', '600', '.', '+', '.', 'gene_id "G1"; transcript_id "T3";'],
        ])

        with self.assertRaises(AssertionError):
            list((segment._get_gene_content(gtf, ['1', 'MT'])))

    def test_no_required_attributes(self):
        """
        Raise error if transcript_id attribute is not present.
        """
        gtf = make_file_from_list([
            ['1', '.', 'transcript', '500', '600', '.', '+', '.', 'gene_id "G1";'],
        ])

        message = "First element in gene content is neither gene or transcript!"
        with self.assertRaisesRegex(Exception, message):
            list((segment._get_gene_content(gtf, ['1', 'MT'])))


class TestGetRegions(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    def test_all_good(self):
        gtf_in_data = list_to_intervals([
            ['1', '.', 'gene', '400', '500', '.', '+', '.', 'gene_id "G2";'],
            ['1', '.', 'transcript', '400', '500', '.', '+', '.', 'gene_id "G2"; transcript_id "T3";'],
            ['1', '.', 'exon', '400', '430', '.', '+', '.', 'gene_id "G2"; transcript_id "T3"; exon_number "1"'],
            ['1', '.', 'CDS', '410', '430', '.', '+', '.', 'gene_id "G2"; transcript_id "T3";'],
            ['1', '.', 'exon', '470', '500', '.', '+', '.', 'gene_id "G2"; transcript_id "T3"; exon_number "2"'],
            ['1', '.', 'CDS', '470', '490', '.', '+', '.', 'gene_id "G2"; transcript_id "T3";'],
        ])
        gtf_in_file = make_file_from_list(intervals_to_list(gtf_in_data))

        gtf_out = get_temp_file_name()

        genome_file = make_file_from_list([
            ['1', '2000'],
            ['MT', '500'],
        ], bedtool=False)

        segment.get_segments(gtf_in_file, gtf_out, genome_file)
        gtf_out_data = list_to_intervals(make_list_from_file(gtf_out, fields_separator='\t'))

        expected = list_to_intervals([
            ['1', '.', 'intergenic', '1', '399', '.', '+', '.', 'gene_id "."; transcript_id ".";'],
            ['1', '.', 'intergenic', '1', '2000', '.', '-', '.', 'gene_id "."; transcript_id ".";'],
            ['1', '.', 'transcript', '400', '500', '.', '+', '.', 'gene_id "G2";transcript_id "T3"; biotype ".";'],
            ['1', '.', 'UTR5', '400', '409', '.', '+', '.',
             'gene_id "G2";exon_number "1";transcript_id "T3"; biotype ".";'],
            ['1', '.', 'gene', '400', '500', '.', '+', '.', 'gene_id "G2"; biotype "[.]";'],
            ['1', '.', 'CDS', '410', '430', '.', '+', '.', 'gene_id "G2";transcript_id "T3"; biotype ".";'],
            ['1', '.', 'intron', '431', '469', '.', '+', '.', 'gene_id "G2"; transcript_id "T3"; biotype ".";'],
            ['1', '.', 'CDS', '470', '490', '.', '+', '.', 'gene_id "G2";transcript_id "T3"; biotype ".";'],
            ['1', '.', 'UTR3', '491', '500', '.', '+', '.',
             'gene_id "G2";exon_number "2";transcript_id "T3"; biotype ".";'],
            ['1', '.', 'intergenic', '501', '2000', '.', '+', '.', 'gene_id "."; transcript_id ".";'],
            ['MT', '.', 'intergenic', '1', '500', '.', '+', '.', 'gene_id "."; transcript_id ".";'],
            ['MT', '.', 'intergenic', '1', '500', '.', '-', '.', 'gene_id "."; transcript_id ".";'],
        ])

        self.assertEqual(expected, gtf_out_data)


if __name__ == '__main__':
    unittest.main()
