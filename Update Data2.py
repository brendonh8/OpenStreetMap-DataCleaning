import csv
import codecs
import pprint
import re
import xml.etree.cElementTree as ET
import cerberus
import schema
import string

OSM_PATH = "denver-boulder_colorado.osm"
NODES_PATH = "nodes.csv"
NODE_TAGS_PATH = "nodes_tags.csv"
WAYS_PATH = "ways.csv"
WAY_NODES_PATH = "ways_nodes.csv"
WAY_TAGS_PATH = "ways_tags.csv"

LOWER_COLON = re.compile(r'^([a-z]|_)+:([a-z]|_)+')
PROBLEMCHARS = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')
street_type_re = re.compile(r'\b\S+\.?$', re.IGNORECASE)
cityRe = re.compile(r',? .+', re.IGNORECASE)

SCHEMA = schema.schema

# Make sure the fields order in the csvs matches the column order in the sql table schema
NODE_FIELDS = ['id', 'lat', 'lon', 'user', 'uid', 'version', 'changeset', 'timestamp']
NODE_TAGS_FIELDS = ['id', 'key', 'value', 'type']
WAY_FIELDS = ['id', 'user', 'uid', 'version', 'changeset', 'timestamp']
WAY_TAGS_FIELDS = ['id', 'key', 'value', 'type']
WAY_NODES_FIELDS = ['id', 'node_id', 'position']

# ====================Update Street Names==================== #


expected = ["Street", "Avenue", "Boulevard", "Drive", "Court", "Place",
            "Square", "Lane", "Road", "Trail", "Parkway", "Commons"]

# UPDATE THIS VARIABLE
mapping = {"Ace": "Avenue",
           "Av": "Avenue",
           "Ave": "Avenue",
           "Ave.": "Avenue",
           "Baselin": "Baseline",
           "Blf": "Bluff",
           "Blvd": "Boulevard",
           "Blvd.": "Boulevard",
           "Camground": "Campground",
           "Cir": "Circle",
           "Ct": "Court",
           "Dr": "Drive",
           "Hwy": "Highway",
           "Ln": "Lane",
           "Pkwy": "Parkway",
           "Pky": "Parkway",
           "Pl": "Place",
           "Raod": "Road",
           "Rd": "Road",
           "Rd.": "Road",
           "Sreet": "Street",
           "St": "Street",
           "St.": "Street",
           "Strret": "Street",
           "ave.": "Avenue",
           "circle": "Circle",
           "ct": "Court",
           "dr": "Drive",
           "drive": "Drive",
           "lane": "Lane",
           "pl": "Place",
           "rd": "Road",
           "road": "Road",
           "st": "Street",
           "trail": "Trail"}


def update_name(name, mapping):

    m = street_type_re.search(name)
    other_st = []
    if m:
        street_type = m.group()
        if street_type in mapping.keys():
            name = re.sub(street_type_re, mapping[street_type], name)
        else:
            other_st.append(street_type)
    return name

# ====================Update City=========================== #


findEnd = re.compile(r'(?i),? (co)*\d*')
cityRe = re.compile(r'\S+ ?')

cityMapping = {"Auroraa": "Aurora",
               "Boulder, Co": "Boulder",
               "Centenn": "Centennial",
               "Hemderson:": "Henderson",
               "Westminstero": "Westminster",
               "Co": "Invalid",
               "+": "Invalid"}


def updateCity(city, cityMapping):
    if type(city) == unicode:
        city = city.encode('ascii', 'ignore')
    # Remove the state at end
    city = re.sub(r'(?i),? (co)*\d*$', '', city)
    city = string.capwords(city)
    city = mapCities(city, cityMapping)
    return city


def mapCities(city, cityMapping):
    m = cityRe.search(city)
    otherCity = []
    if m:
        cityName = m.group()
        if cityName in cityMapping.keys():
            # Correct specific names
            city = re.sub(cityRe, cityMapping[cityName], city)
        else:
            otherCity.append(cityName)
    return city

# ====================Update Phone========================== #


def correctPhone(phone):
    phone = phone.encode('utf8')
    # Find double entries
    findMultiples = re.compile(r'[\;]')
    match = re.search(findMultiples, phone)
    # Remove invlaid numbers
    if len(phone) < 10 and phone != 911:
        del phone
        return
    else:
        if match:
            phone = fixProblems(phone.split(match.group()))
            return phone
        else:
            phone = phone
    phone = standardize(phone)
    return phone


def fixProblems(numbLst):
    # Find numbers with common format
    correctFormat = re.compile(r'^(\+1) /(\d{3}/) \d{3}-\d{4}')
    newLst = []
    for number in numbLst:
        match = re.search(correctFormat, number)
        if match:
            newLst.append(number)
        else:
            newNumber = standardize(number)
            newLst.append(newNumber)
    return newLst


def standardize(phone):
    # Remove everything but the number
    phone = [item.replace('(', '').replace(
        ')', '').replace(' ', '').replace('-', '').replace('.', '')
        for item in phone]
    phone = "".join(phone)
    # Put numbers to same format
    if phone.startswith('+01'):
        phone = '+1 ' + '(' + str(phone[3:6]) + ')' + ' ' \
                + str(phone[6:9]) + '-' + str(phone[9:])
    elif phone.startswith('+1'):
        phone = '+1 ' + '(' + str(phone[2:5]) + ')' + ' ' \
                + str(phone[5:8]) + '-' + str(phone[8:])
    elif phone.startswith('1'):
        phone = '+1 ' + '(' + str(phone[1:4]) + ')' + ' ' \
                + str(phone[4:7]) + '-' + str(phone[7:])
    else:
        phone = '+1 ' + '(' + str(phone[:3]) + ')' + ' ' \
                + str(phone[3:6]) + '-' + str(phone[6:])
    return phone


# ====================Shape Element========================= #


def shape_element(element, node_attr_fields=NODE_FIELDS, way_attr_fields=WAY_FIELDS,
                  problem_chars=PROBLEMCHARS, default_tag_type='regular'):
    """Clean and shape node or way XML element to Python dict"""

    node_attribs = {}
    way_attribs = {}
    way_nodes = []
    tags = []  # Handle secondary tags the same way for both node and way elements

    if element.tag == 'node':
        for attrib in element.attrib:
            if attrib in NODE_FIELDS:
                node_attribs[attrib] = element.attrib[attrib]
        for child in element:
            node_tags = {}
            if PROBLEMCHARS.match(child.attrib['k']):
                continue
            elif LOWER_COLON.match(child.attrib['k']):
                node_tags['id'] = element.attrib['id']
                node_tags['key'] = child.attrib['k'].split(":", 1)[1]
                node_tags['type'] = child.attrib['k'].split(":", 1)[0]
                if child.attrib['k'] == 'addr:street':
                    node_tags['value'] = update_name(child.attrib['v'], mapping)
                elif child.attrib['k'] == 'addr:city':
                    node_tags['value'] = updateCity(child.attrib['v'], cityMapping)
                else:
                    node_tags['value'] = child.attrib['v']
                tags.append(node_tags)
            else:
                node_tags['type'] = 'regular'
                node_tags['key'] = child.attrib['k']
                node_tags['id'] = element.attrib['id']
                if child.attrib['k'] == 'phone':
                    node_tags['value'] = correctPhone(child.attrib['v'])
                else:
                    node_tags['value'] = child.attrib['v']
                tags.append(node_tags)

        return {'node': node_attribs, 'node_tags': tags}

    elif element.tag == 'way':
        for attrib in element.attrib:
            if attrib in WAY_FIELDS:
                way_attribs[attrib] = element.attrib[attrib]

        count = 0
        for child in element:
            way_tag = {}
            way_node = {}

            if child.tag == 'tag':
                if PROBLEMCHARS.match(child.attrib['k']):
                    continue
                elif LOWER_COLON.match(child.attrib['k']):
                    way_tag['id'] = element.attrib['id']
                    way_tag['key'] = child.attrib['k'].split(":", 1)[1]
                    way_tag['type'] = child.attrib['k'].split(":", 1)[0]
                    if child.attrib['k'] == 'addr:street':
                        way_tag['value'] = update_name(child.attrib['v'], mapping)
                    elif child.attrib['k'] == 'addr:city':
                        way_tag['value'] = updateCity(child.attrib['v'], cityMapping)
                    else:
                        way_tag['value'] = child.attrib['v']
                    tags.append(way_tag)
                else:
                    way_tag['type'] = 'regular'
                    way_tag['key'] = child.attrib['k']
                    way_tag['id'] = element.attrib['id']
                    if child.attrib['k'] == 'phone':
                        way_tag['value'] = correctPhone(child.attrib['v'])
                    else:
                        way_tag['value'] = child.attrib['v']
                    tags.append(way_tag)
            elif child.tag == 'nd':
                way_node['id'] = element.attrib['id']
                way_node['node_id'] = child.attrib['ref']
                way_node['position'] = count
                count += 1
                way_nodes.append(way_node)

        return {'way': way_attribs, 'way_nodes': way_nodes, 'way_tags': tags}

# ================================================== #
#               Helper Functions                     #
# ================================================== #


def get_element(osm_file, tags=('node', 'way', 'relation')):
    """Yield element if it is the right type of tag"""

    context = ET.iterparse(osm_file, events=('start', 'end'))
    _, root = next(context)
    for event, elem in context:
        if event == 'end' and elem.tag in tags:
            yield elem
            root.clear()


def validate_element(element, validator, schema=SCHEMA):
    """Raise ValidationError if element does not match schema"""
    if validator.validate(element, schema) is not True:
        field, errors = next(validator.errors.iteritems())
        message_string = "\nElement of type '{0}' has the following errors:\n{1}"
        error_string = pprint.pformat(errors)

        raise Exception(message_string.format(field, error_string))


class UnicodeDictWriter(csv.DictWriter, object):
    """Extend csv.DictWriter to handle Unicode input"""

    def writerow(self, row):
        super(UnicodeDictWriter, self).writerow({
            k: (v.encode('utf-8') if isinstance(v, unicode) else v) for k, v in row.iteritems()
        })

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


# ================================================== #
#               Main Function                        #
# ================================================== #
def process_map(file_in, validate):
    """Iteratively process each XML element and write to csv(s)"""

    with codecs.open(NODES_PATH, 'w') as nodes_file, \
        codecs.open(NODE_TAGS_PATH, 'w') as nodes_tags_file, \
        codecs.open(WAYS_PATH, 'w') as ways_file, \
        codecs.open(WAY_NODES_PATH, 'w') as way_nodes_file, \
            codecs.open(WAY_TAGS_PATH, 'w') as way_tags_file:

        nodes_writer = UnicodeDictWriter(nodes_file, NODE_FIELDS)
        node_tags_writer = UnicodeDictWriter(nodes_tags_file, NODE_TAGS_FIELDS)
        ways_writer = UnicodeDictWriter(ways_file, WAY_FIELDS)
        way_nodes_writer = UnicodeDictWriter(way_nodes_file, WAY_NODES_FIELDS)
        way_tags_writer = UnicodeDictWriter(way_tags_file, WAY_TAGS_FIELDS)

        nodes_writer.writeheader()
        node_tags_writer.writeheader()
        ways_writer.writeheader()
        way_nodes_writer.writeheader()
        way_tags_writer.writeheader()

        validator = cerberus.Validator()

        for element in get_element(file_in, tags=('node', 'way')):
            el = shape_element(element)
            if el:
                if validate is True:
                    validate_element(el, validator)

                if element.tag == 'node':
                    nodes_writer.writerow(el['node'])
                    node_tags_writer.writerows(el['node_tags'])
                elif element.tag == 'way':
                    ways_writer.writerow(el['way'])
                    way_nodes_writer.writerows(el['way_nodes'])
                    way_tags_writer.writerows(el['way_tags'])


if __name__ == '__main__':
    # Note: Validation is ~ 10X slower. For the project consider using a small
    # sample of the map when validating.
    process_map(OSM_PATH, validate=False)
