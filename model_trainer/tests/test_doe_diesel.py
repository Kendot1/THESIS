import unittest
import xml.etree.ElementTree as ET

from external_context.extract_doe_diesel import parse_page, parse_period

NS='{http://www.w3.org/1999/xhtml}'


def page(low='58.70',high='61.25',city='Batac City',company=('61.25','58.70'),with_date=True):
    root=ET.Element(NS+'page')
    def line(text,x,y,width=20):
        attrs={'xMin':str(x),'xMax':str(x+width),'yMin':str(y),'yMax':str(y+5)}
        node=ET.SubElement(root,NS+'line',attrs)
        ET.SubElement(node,NS+'word',attrs).text=text
    line('PRODUCT',125,55);line('PROVINCE',45,68);line('Cities',94,68,10)
    line('PETRON',180,55,20)
    line('IND',675,55,8);line('OVERALL RANGE',725,59,40);line('COMMON',785,56,20)
    if with_date:line('Date of Monitoring: December 5 - 7, 2023',39,45,150)
    for i,p in enumerate(['RON 100','RON 97','RON 95','RON 91','DIESEL','DIESEL PLUS','KEROSENE']):line(p,120,78+7*i,30)
    if city:line(city,80,99,35)
    line('Region I',455,71)
    for x,value in zip([180,230],company):line(value,x,106.4,10)
    for x,value in [(723,low),(744,'-'),(757,high)]:line(value,x,106.4,10 if value!='-' else 2)
    return root


class DOEDieselTests(unittest.TestCase):
    def test_explicit_monitoring_dates(self):
        self.assertEqual(parse_period('Date of Monitoring: December 5 - 7, 2023'),('2023-12-05','2023-12-07'))
        self.assertEqual(parse_period('November 26 to December 2, 2024'),('2024-11-26','2024-12-02'))
        self.assertEqual(parse_period('January 23, 2024'),('2024-01-23','2024-01-23'))
        for text in ['December 31 - 2, 2023','February 30, 2024','January 1 - 30, 2024','January 2024']:
            with self.assertRaises(ValueError):parse_period(text)

    def test_range_matches_company_extrema(self):
        rows=parse_page(page(),1)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['range_low'],58.7)
        self.assertEqual(rows[0]['range_high'],61.25)
        self.assertEqual(rows[0]['city_literal'],'Batac City')
        self.assertFalse(rows[0]['training_admitted'])
        self.assertFalse(rows[0]['unit_verified'])

    def test_zero_placeholder_is_missing_not_free_diesel(self):
        row=parse_page(page('0.00','0.00',company=()),1)[0]
        self.assertIsNone(row['range_low'])
        self.assertEqual(row['missing_reason'],'zero_placeholder_no_outlet_prices')

    def test_inconsistent_extrema_rejected(self):
        row=parse_page(page('58.70','62.25'),1)[0]
        self.assertEqual(row['status'],'rejected')
        self.assertIn('extrema',row['reason'])

    def test_reversed_or_half_zero_range_rejected(self):
        for low,high in [('62.25','58.70'),('0.00','61.25')]:
            self.assertEqual(parse_page(page(low,high),1)[0]['status'],'rejected')

    def test_ambiguous_city_not_filled(self):
        self.assertEqual(parse_page(page(city=None),1)[0]['status'],'rejected')

    def test_continuation_date_requires_explicit_document_context(self):
        with self.assertRaises(ValueError):parse_page(page(with_date=False),2)
        row=parse_page(page(with_date=False),2,'Date of Monitoring: December 5 - 7, 2023')[0]
        self.assertEqual(row['monitoring_period_basis'],'unique_monitoring_header_in_same_PDF')

    def test_repeated_geography_headers_in_later_sections(self):
        p=page()
        for text,x in [('Cities',94),('PROVINCE',45)]:
            attrs={'xMin':str(x),'xMax':str(x+10),'yMin':'235','yMax':'240'}
            line=ET.SubElement(p,NS+'line',attrs);ET.SubElement(line,NS+'word',attrs).text=text
        self.assertEqual(parse_page(p,1)[0]['status'],'candidate')

    def test_wrapped_headers_and_week_date(self):
        p=page(with_date=False)
        for line in list(p):
            if line[0].text in ['OVERALL RANGE','Cities']:p.remove(line)
        def add(text,x,y,width):
            attrs={'xMin':str(x),'xMax':str(x+width),'yMin':str(y),'yMax':str(y+5)}
            line=ET.SubElement(p,NS+'line',attrs);ET.SubElement(line,NS+'word',attrs).text=text
        add('OVERALL',725,55,40);add('RANGE',730,62,30)
        add('CITY /',90,55,20);add('MUNICIPALITY',80,62,35)
        add('(For the week: Tuesday - Monday) as of November 26 to December 2, 2024',30,40,200)
        add('Date of Monitoring:____________________',30,500,150)
        row=parse_page(p,1)[0]
        self.assertEqual(row['status'],'candidate')
        self.assertEqual(row['reference_start'],'2024-11-26')
        self.assertEqual(row['reference_end'],'2024-12-02')

    def test_company_prices_merged_into_product_line(self):
        p=page()
        diesel=next(l for l in p if l[0].text=='DIESEL')
        attrs={'xMin':'180','xMax':'190','yMin':'106.4','yMax':'111.4'}
        ET.SubElement(diesel,NS+'word',attrs).text='61.25'
        diesel.set('xMax','190')
        self.assertEqual(parse_page(p,1)[0]['status'],'candidate')

    def test_conflicting_monitoring_headers_rejected(self):
        p=page()
        attrs={'xMin':'30','xMax':'200','yMin':'40','yMax':'45'}
        line=ET.SubElement(p,NS+'line',attrs)
        ET.SubElement(line,NS+'word',attrs).text='(For the week: Tuesday - Monday) as of December 12 to 18, 2023'
        with self.assertRaisesRegex(ValueError,'monitoring date'):parse_page(p,1)

    def test_disjoint_wrapped_header_is_rejected(self):
        p=page()
        original=next(l for l in p if l[0].text=='OVERALL RANGE');p.remove(original)
        for text,x,y in [('OVERALL',725,55),('RANGE',900,62)]:
            attrs={'xMin':str(x),'xMax':str(x+20),'yMin':str(y),'yMax':str(y+5)}
            line=ET.SubElement(p,NS+'line',attrs);ET.SubElement(line,NS+'word',attrs).text=text
        with self.assertRaisesRegex(ValueError,'OVERALL RANGE'):parse_page(p,1)

    def test_printed_rainge_spelling_preserved(self):
        p=page()
        header=next(l for l in p if l[0].text=='OVERALL RANGE')
        header[0].text='OVERALL RAINGE'
        row=parse_page(p,1)[0]
        self.assertEqual(row['status'],'candidate')
        self.assertEqual(row['overall_header_literal'],'OVERALL RAINGE')

    def test_merged_independent_and_overall_header(self):
        p=page()
        header=next(l for l in p if l[0].text=='OVERALL RANGE');p.remove(header)
        ind=next(l for l in p if l[0].text=='IND')
        for text,x,width in [('OVERALL',725,20),('RAINGE',748,17)]:
            attrs={'xMin':str(x),'xMax':str(x+width),'yMin':'55','yMax':'60'}
            ET.SubElement(ind,NS+'word',attrs).text=text
        ind.set('xMax','765')
        row=parse_page(p,1)[0]
        self.assertEqual(row['status'],'candidate')
        self.assertEqual(row['range_low'],58.7)
        self.assertEqual(row['overall_header_literal'],'OVERALL RAINGE')

    def test_adjacent_header_cells_merge_into_one_line(self):
        p=page()
        for l in list(p):
            if l[0].text in ['PROVINCE','Cities','OVERALL RANGE','COMMON']:p.remove(l)
        for entries,y in [([('PROVINCE',45,20),('CITY',80,10),('/',91,2),('MUNICIPALITY',94,20)],55),
                          ([('OVERALL',725,40),('COMMON',785,20)],55),
                          ([('RANGE',730,30)],62)]:
            line=ET.SubElement(p,NS+'line',{'xMin':str(entries[0][1]),'xMax':str(entries[-1][1]+entries[-1][2]),'yMin':str(y),'yMax':str(y+5)})
            for text,x,width in entries:
                ET.SubElement(line,NS+'word',{'xMin':str(x),'xMax':str(x+width),'yMin':str(y),'yMax':str(y+5)}).text=text
        self.assertEqual(parse_page(p,1)[0]['status'],'candidate')


if __name__=='__main__':unittest.main()
