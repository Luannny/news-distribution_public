import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch, Mock

from src.research import (Paper, from_epmc, from_crossref, parse_arxiv, candidate_pool, topic_of,
                          validate_selection, save_state, load_state, render_digest, main)

TODAY = date(2026, 10, 29)


def record(**changes):
    item = {"id": "12345", "source": "MED", "title": "Frequency-resolved ultrafast electron diffraction",
            "abstractText": "Ultrafast electron diffraction measurements resolve molecular vibrational dynamics. " * 8,
            "journalInfo": {"journal": {"title": "Faraday Discussions"}},
            "firstPublicationDate": "2026-10-20", "doi": "10.1039/example", "authorString": "A. Researcher",
            "pubTypeList": {"pubType": ["Journal Article"]}}
    item.update(changes)
    return item


def paper(index=1, status="期刊论文", journal="Faraday Discussions"):
    return Paper("epmc:MED:" + str(index), "Ultrafast electron diffraction " + str(index), "evidence "*60,
                 journal, "2026-10-20", "Researcher", "10.1000/" + str(index), "超快电镜与电子衍射", status,
                 "https://europepmc.org/article/MED/"+str(index), date_note="首次发表日期")


def selection(index, score=8):
    return {"id": index, "relevance": score, "merit": score, "title": "超快电子衍射研究导读",
            "method": "作者通过超快电子衍射测量分子结构", "finding": "作者报告了一项具体的实验观测结果",
            "value": "对分子结构动力学分析具有参考价值", "limits": "摘要未说明测量重复性，精读时应核查"}


class ResearchTests(unittest.TestCase):
    def test_ued_in_abstract_is_not_buried_under_generic_ultrafast(self):
        self.assertEqual(topic_of('Ultrafast Dynamics of Bond Dissociation', 'We use ultrafast electron diffraction to measure structure.'), '超快电镜与电子衍射')

    def test_arxiv_update_does_not_turn_old_paper_into_new_paper(self):
        xml = '''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/2601.12345v3</id><title>Ultrafast electron diffraction</title><published>2026-01-20T00:00:00Z</published><updated>2026-10-29T00:00:00Z</updated><summary>''' + 'Experimental ultrafast electron diffraction. '*20 + '''</summary></entry></feed>'''
        self.assertEqual(parse_arxiv(xml, TODAY), [])

    def test_journal_identity_is_from_metadata_not_keyword(self):
        self.assertIsNotNone(from_epmc(record(), TODAY))
        self.assertIsNone(from_epmc(record(journalInfo={"journal": {"title": "Unknown Nature Journal"}}), TODAY))

    def test_old_future_short_and_corrections_rejected(self):
        for changes in ({"firstPublicationDate":"2026-08-01"}, {"firstPublicationDate":"2026-11-01"},
                        {"title":"Author Correction: Ultrafast electron diffraction"},
                        {"abstractText":"Only a headline"}, {"isRetracted":"Y"}):
            self.assertIsNone(from_epmc(record(**changes), TODAY))

    def test_month_precision_not_misrepresented_as_exact_day(self):
        p = from_epmc(record(firstPublicationDate="2026-10-01", journalInfo={"journal":{"title":"Faraday Discussions"}, "dateOfPublication":"2026 Oct"}), TODAY)
        self.assertEqual(p.published, "2026-10")
        self.assertIn("月", p.date_note)

    def test_biorxiv_label_and_oa_status_are_immutable(self):
        p = from_epmc(record(source="PPR", doi="10.1101/12345", journalInfo={}, pmcid="PMC123", isOpenAccess="N"), TODAY)
        self.assertIn("尚未同行评审", p.status)
        self.assertEqual(p.fulltext_url, "")
        self.assertIsNone(from_epmc(record(source="PPR", doi="10.5555/example", journalInfo={}), TODAY))

    def test_fulltext_link_requires_explicit_open_access(self):
        p = from_epmc(record(pmcid="PMC12345", isOpenAccess="Y"), TODAY)
        self.assertEqual(p.fulltext_url, "https://europepmc.org/articles/PMC12345")

    def test_same_paper_across_sources_and_sent_history_removed(self):
        a = paper()
        b = Paper(**{**a.__dict__, "id":"doi:"+a.doi, "journal":"Faraday discussions"})
        self.assertEqual(len(candidate_pool([a,b], {})), 1)
        self.assertEqual(candidate_pool([a,b], {a.keys()[0]:"2026-10-28"}), [])

    def test_arxiv_version_keys_do_not_collapse_unrelated_papers(self):
        a = Paper(**{**paper().__dict__, "id":"arxiv:2610.12345v2"})
        b = Paper(**{**paper(2).__dict__, "id":"arxiv:2610.12346v1"})
        self.assertIn("arxiv:2610.12345", a.keys())
        self.assertEqual(len(candidate_pool([a,b], {})), 2)

    def test_selection_rejects_hallucinated_duplicate_or_negative_ids(self):
        for ids in ([-1],[8],[0,0]):
            with self.assertRaises(ValueError):
                validate_selection({"papers":[selection(i) for i in ids]}, [paper()])

    def test_preprints_need_two_journal_papers_and_at_most_one(self):
        pool = [paper(), paper(2,journal="Nature Methods"), paper(3,status="预印本，尚未同行评审",journal="arXiv"), paper(4,status="预印本，尚未同行评审",journal="bioRxiv")]
        pool[2] = Paper(**{**pool[2].__dict__, 'topic':'蛋白折叠与生物化学'})
        pool[3] = Paper(**{**pool[3].__dict__, 'topic':'超快科学与物理化学'})
        rows = validate_selection({"papers":[selection(i) for i in range(4)]}, pool)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(validate_selection({"papers":[selection(0),selection(2)]},pool)),1)

    def test_english_body_is_rejected_before_delivery(self):
        row=selection(0);row['method']='The authors use ultrafast electron diffraction.'
        with self.assertRaises(ValueError): validate_selection({'papers':[row]},[paper()])

    def test_known_scientific_mistranslations_are_not_sent(self):
        p=Paper(**{**paper().__dict__,'abstract':'We model allene with ab initio multiple spawning. '*15})
        for phrase in ('通过对全能分子开展电子衍射实验进行观测','作者结合从头算多重孵化方法进行动力学计算'):
            row=selection(0);row['method']=phrase
            with self.assertRaises(ValueError): validate_selection({'papers':[row]},[p])

    def test_one_topic_cannot_fill_the_digest(self):
        pool=[paper(i,journal='Nature Methods' if i%2 else 'Faraday Discussions') for i in range(4)]
        self.assertEqual(len(validate_selection({'papers':[selection(i) for i in range(4)]},pool)),2)

    def test_low_quality_and_journal_flood_filtered(self):
        pool=[paper(i) for i in range(5)]
        rows=validate_selection({"papers":[selection(i) for i in range(5)]},pool)
        self.assertEqual(len(rows),2)
        self.assertEqual(validate_selection({"papers":[selection(0,6)]},pool),[])

    def test_invalid_state_fails_closed_and_success_history_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state.json"
            save_state({},[paper()],TODAY,path)
            self.assertEqual(load_state(path)[paper().keys()[0]], str(TODAY))
            path.write_text('[]')
            with self.assertRaises(ValueError): load_state(path)

    def test_crossref_uses_earliest_publication_not_metadata_update(self):
        item={"title":["Ultrafast electron diffraction"],"abstract":"experimental evidence "*30,"DOI":"10.1234/test",
              "type":"journal-article","container-title":["Physical Review Letters"],
              "published-online":{"date-parts":[[2026,8,1]]},"published-print":{"date-parts":[[2026,10,20]]}}
        self.assertIsNone(from_crossref(item,TODAY))

    def test_dry_run_never_sends_or_marks_papers_sent(self):
        with tempfile.TemporaryDirectory() as tmp, patch('src.research.get_ai_settings', return_value=Mock()), \
             patch('src.research.collect_papers', return_value=([paper()],[])), \
             patch('src.research.load_state', return_value={}), \
             patch('src.research.select_papers', return_value=[(paper(),selection(0))]), \
             patch('src.research.send_email') as send, patch('src.research.save_state') as save:
            path=Path(tmp)/'preview.html'
            with patch('sys.argv',['research','--dry-run','--preview-path',str(path)]): main()
            send.assert_not_called();save.assert_not_called()
            self.assertIn("未发送邮件",path.with_suffix('.md').read_text())
            self.assertIn("免费摘要",path.read_text())

    def test_renderer_escapes_model_and_source_html(self):
        row=selection(0);row['title']='<script>oops</script>'
        _,doc,_=render_digest([(paper(),row)],TODAY,[])
        self.assertNotIn('<script>',doc)
        self.assertIn('&lt;script&gt;',doc)


if __name__ == '__main__':
    unittest.main()
