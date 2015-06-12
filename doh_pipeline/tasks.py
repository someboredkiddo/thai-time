import csv
import itertools
import logging
import pprint
import urllib

import luigi
import MySQLdb


log_doh = logging.getLogger('doh')

class GetHealthGradeFile(luigi.Task):
    """
    Task to grab restaurant data
    """

    #inspection_date = luigi.DateParameter()
    reload = luigi.BooleanParameter(default=False, significant=False) #will force a redownload

    def __init__(self, *args, **kwargs):
        super(GetHealthGradeFile, self).__init__(*args, **kwargs)
        if self.reload == True:
            if self.output().exists():
                self.output().remove()

    def run(self):
        conf = luigi.configuration.get_config()
        file_url = conf.get('doh', 'download_url')
        self.output().makedirs()
        testfile = urllib.URLopener()
        log_doh.info("Starting download of DOH file %s", file_url)
        testfile.retrieve(file_url, self.output().fn)
        log_doh.info("Finished download of DOH file %s", file_url)

    def output(self):
        config = luigi.configuration.get_config()
        return luigi.LocalTarget("%s/doh_download.csv" % config.get('doh', 'data_dir'))


class TransformHealthGrades(luigi.Task):
    """
    Task to clean health grades data and dump it into files to be loaded to db
    """

    #inspection_date = luigi.DateParameter()
    reload = luigi.BooleanParameter(default=False, significant=False) #will force a redownload

    line_schema = [
        {"field": "camis", "type": "INT"},
        {"field": "dba", "type": "VARCHAR"},
        {"field": "boro", "type": "VARCHAR"},
        {"field": "building", "type": "VARCHAR"},
        {"field": "street", "type": "VARCHAR"},
        {"field": "zipcode", "type": "INT"},
        {"field": "phone", "type": "VARCHAR"},
        {"field": "cuisine_description", "type": "VARCHAR"},
        {"field": "inspection_date", "type": "DATE"},
        {"field": "action", "type": "VARCHAR"},
        {"field": "violation_code", "type": "INT"},
        {"field": "violation_description", "type": "VARCHAR"},
        {"field": "critical_flag", "type": "VARCHAR"},
        {"field": "score", "type": "INT"},
        {"field": "grade", "type": "VARCHAR"},
        {"field": "grade_date", "type": "DATE"},
        {"field": "record_date", "type": "DATE"},
        {"field": "inspection_type", "type": "VARCHAR"}
    ]

    def __init__(self, *args, **kwargs):
        super(TransformHealthGrades, self).__init__(*args, **kwargs)
        if self.reload == True:
            for file in self.output().values():
                if file.exists():
                    file.remove()

    def requires(self):
        return GetHealthGradeFile(reload=self.reload)

    def run(self):
        prev_parsed_line = None
        n = 0
        with self.input().open('r') as in_file, \
             self.output()['restaurant'].open('w') as reastaurant_file, \
             self.output()['inspection'].open('w') as inspection_file, \
             self.output()['violation'].open('w') as violation_file:
            reader = csv.reader(in_file)
            next(reader) #skip header row
            # TODO: Parsing assumes data input ordered by camis then date,
            # need to add checks for this
            for line in reader:
                parsed_line = self.parse_line(line)
                n += 1
                if parsed_line != None:
                    #output files
                    self.output_restaurant(parsed_line, prev_parsed_line, file=reastaurant_file)
                    self.output_inspection(parsed_line, prev_parsed_line, file=inspection_file)
                    self.output_violation(parsed_line, file=violation_file)
                prev_parsed_line = parsed_line
            log_doh.info("Processed %s records", n)

    def parse_line(self, line):
        result = {}
        n = 0
        for element in line:
            log_doh.debug("Parse Line %s %s", n, element)
            #logging.info(self.line_schema[n]['field'])
            result[self.line_schema[n]['field']] = self.clean_elements(element,
                                                                       self.line_schema[n]['field'],
                                                                       self.line_schema[n]['type'])
            n += 1
        return result

    #TODO: need to clean better for ints & varchars
    def clean_elements(self, element, field, type):
        element = str.strip(element)
        # TODO: Clean empty elements better
        if element == "":
            if field == "grade":
                element = "Unknown"
            return element
        if field == "grade" and element == "Z":
            element = "Pending"
        elif type == 'DATE':
            log_doh.debug("Cleaning %s %s", element, type)
            # parse(parsed_line['inspection_date']).strftime("%Y-%m-%d") very slow
            # element = datetime.strptime(element, '%m/%d/%Y').strftime('%Y/%m/%d') okayish
            # TODO: precompiled regex may be a little faster
            date_split = element.split("/")
            element = "%s/%s/%s" % (date_split[2], date_split[0], date_split[1])
        return element

    def output_restaurant(self, parsed_line, prev_parsed_line, file=None):
        display = False
        #first record in file
        if prev_parsed_line is None:
            display = True
        #new restaurant in list, let's save it
        elif parsed_line['camis'] != prev_parsed_line['camis']:
            display = True

        if display == False:
            return None

        restaurant = ("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (
            parsed_line['camis'],
            parsed_line['dba'],
            parsed_line['boro'],
            parsed_line['building'],
            parsed_line['street'],
            parsed_line['zipcode'],
            parsed_line['phone'],
            parsed_line['cuisine_description'],
            parsed_line['inspection_date'])) #assume first entry has latest inspection dt
        if file is not None:
            file.write(restaurant)
        return restaurant

    def output_inspection(self, parsed_line, prev_parsed_line, file=None):
        display = False
        #first record in file
        if prev_parsed_line is None:
            display = True
        #new restaurant in list, let's save the inspection
        elif parsed_line['camis'] != prev_parsed_line['camis']:
            display = True
        #same restaurant, new inspection
        elif  parsed_line['inspection_date'] != prev_parsed_line['inspection_date']:
            display = True

        if display == False:
            return None

        inspection = ("%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (
            parsed_line['camis'],
            parsed_line['inspection_date'],
            parsed_line['action'],
            parsed_line['score'],
            parsed_line['grade'],
            parsed_line['grade_date'],
            parsed_line['inspection_type']))
        if file is not None:
            file.write(inspection)
        return inspection

    def output_violation(self, parsed_line, file=None):
        # indicates no violations [yeah right]
        if parsed_line['violation_code'] == '':
            return None

        violation = ("%s\t%s\t%s\t%s\t%s\n" % (
            parsed_line['camis'],
            parsed_line['inspection_date'],
            parsed_line['violation_code'],
            parsed_line['violation_description'],
            parsed_line['critical_flag']))
        if file is not None:
            file.write(violation)
        return violation

    def output(self):
        config = luigi.configuration.get_config()
        return {'restaurant' : luigi.LocalTarget("%s/restaurant.csv" % config.get('doh', 'data_dir')),
                'inspection' : luigi.LocalTarget("%s/inspection.csv" % config.get('doh', 'data_dir')),
                'violation' : luigi.LocalTarget("%s/violation.csv" % config.get('doh', 'data_dir'))}


class LoadMysqlTask(luigi.Task):
    """
    Base class for loading text file output into mysql.  Would be fun to abstract more later.
    """

    batch_size = 2000
    columns = [] #TODO: get from db?
    table = ""
    upsert = False
    upsert_columns = []


    reload = luigi.BooleanParameter(default=False, significant=False) #will force a reload of data

    def __init__(self, *args, **kwargs):
        super(LoadMysqlTask, self).__init__(*args, **kwargs)
        if self.reload == True:
            if self.output().exists():
                self.output().remove()

    def requires(self):
        return TransformHealthGrades(reload=self.reload)

    def run(self):
        # load infile would be faster, but MySQLdb will take care of escaping
        # and input is pretty smalls
        config = luigi.configuration.get_config()

        db = MySQLdb.connect(config.get('db', 'host'),
                             config.get('db', 'user'),
                             config.get('db', 'pass'),
                             config.get('db', 'name'))
        cursor = db.cursor(MySQLdb.cursors.DictCursor)

        if self.reload:
            log_doh.info("Truncating %s", self.table)
            cursor.execute("TRUNCATE TABLE %s" % self.table)
            db.commit()

        sql = "INSERT INTO %s " % self.table
        sql += "(%s) " % ",".join(self.columns)
        sql += "VALUES (%s) " % ",".join(list(itertools.repeat("%s", len(self.columns))))
        if self.upsert:
            sql += " ON DUPLICATE KEY UPDATE "
            for column in self.upsert_columns:
                sql += "%s.%s = VALUES(%s.%s)," % (self.table, column, self.table, column)
            sql = sql[:-1]

        n = 0
        rows = []
        #TODO: Abstract input to make this more of a library class
        with self.input()[self.table].open('r') as in_file:
            for line in in_file:
                rows.append(line.strip("\n").split("\t"))
                if n % self.batch_size == 0:
                    log_doh.debug("SQL: %s", sql)
                    log_doh.debug("Rows: %s", rows)
                    cursor.executemany(sql, rows)
                    log_doh.debug("Inserted %s rows into %s table", self.table, self.batch_size)
                    rows = []
                n += 1
            num_rows_left = len(rows)
            if num_rows_left > 0:
                cursor.executemany(sql, rows)
                log_doh.debug("Inserted %s rows into table %s", self.table, num_rows_left)
        log_doh.info("Inserted %s rows into table %s", n, self.table)

        db.commit()
        db.close()

        #mark checkpoint as complete so task doesn't rerun repeatedly
        with self.output().open('w') as out_file:
            print >> out_file, "donzo"

    def output(self):
        config = luigi.configuration.get_config()
        return luigi.LocalTarget("%s/load_%s.checkpoint" % (config.get('doh', 'data_dir'), self.table))

class LoadViolations(LoadMysqlTask):
    """
    Luigi task to load violations data from text file into the db
    """

    batch_size = 5000
    table = 'violation'
    columns = ['camis',
               'inspection_date',
               'violation_code',
               'violation_description',
               'critical_flag']


class LoadInspections(LoadMysqlTask):
    """
    Luigi task to load inspections data from text file into the db
    """

    batch_size = 2000
    table = 'inspection'
    columns = ['camis',
               'inspection_date',
               'action',
               'score',
               'grade',
               'grade_date',
               'inspection_type']


#TODO: Continue subclassing LoadMysqlTask (add upsert functionality)
class LoadRestaurants(LoadMysqlTask):
    """
    Luigi task to load restaurant data into the db
    """

    reload = luigi.BooleanParameter(default=False, significant=False) #will force a reload of data

    batch_size = 2000
    table = "restaurant"
    columns = ["camis",
                "dba",
                "boro",
                "building",
                "street",
                "zipcode",
                "phone",
                "cuisine",
                "last_inspection_date"]
    upsert = True
    upsert_columns = ["dba",
                      "boro",
                      "building",
                      "street",
                      "zipcode",
                      "phone",
                      "cuisine",
                      "last_inspection_date"]


class UpdateHealthGrades(luigi.WrapperTask):
    """
    Task to launch all other tasks for the DOH pipeline
    """

    #TODO: add ability to only load data after a certain inspection date
    #inspection_date = luigi.DateParameter()

    #will force a reload of all data
    reload = luigi.BooleanParameter(default=False, significant=False)

    def requires(self):
        tasks = [LoadRestaurants(reload=self.reload),
                 LoadViolations(reload=self.reload),
                 LoadInspections(reload=self.reload)]
        return tasks


if __name__ == "__main__":
    luigi.run()
