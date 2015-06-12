""" Tornado App to display DOH Restaurant Grades/Inspections for Thai Restaurants """

import os
import pprint

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text
import tornado.ioloop
from tornado.options import define, options
import tornado.web

from models import Restaurant, Inspection, Violation


#global db
DB_SESSION = None

class InspectionHandler(tornado.web.RequestHandler):
    """
    Web handler to return inspections/violations associated with a restaurant

    Params
    camis - camis associated with restaurant
    """

    def get(self):
        camis = self.get_argument("camis")

        inspections = query = DB_SESSION.query(Inspection).\
            filter(Inspection.camis == camis).\
            order_by(Inspection.inspection_date.desc())

        inspection_results = []
        for i in inspections:
            # This is a lot of queries, could probably turn into one query
            violations = query = DB_SESSION.query(Violation).\
                filter(Violation.camis == camis).\
                filter(Violation.inspection_date == i.inspection_date).\
                order_by(Violation.critical_flag.asc())
            violation_results = []
            for v in violations:
                violation_results.append({
                    "critical_flag" : v.critical_flag,
                    "violation_code" : v.violation_code,
                    "violation_description" : v.violation_description})

            inspection_results.append({
                "inspection_date" : i.inspection_date,
                "action" : i.action,
                "score": i.score,
                "grade": i.grade,
                "type" : i.inspection_type,
                "violations" : violation_results})
        DB_SESSION.commit()
        self.render("inspection.html", inspection_results=inspection_results)


class ThaiTimeHandler(tornado.web.RequestHandler):
    """
    Web handler to Display all the Thai restaurants in NYC and corresponding DOH info
    """

    def get(self):
        order_request = self.get_argument("Rank", default="name")
        if order_request == 'name':
            order_by = text("restaurant.dba")
        elif order_request == 'current_grade':
            order_by = text("inspection.grade asc, inspection.score asc")
        elif order_request == 'current_score':
            order_by = text("inspection.score asc")

        grades = self.get_arguments("GradeFilter")
        if not grades:
            grades = ("A","B")

        query = DB_SESSION.query(Restaurant, Inspection).\
            filter(Restaurant.camis == Inspection.camis).\
            filter(Restaurant.last_inspection_date == Inspection.inspection_date).\
            filter(Restaurant.cuisine == 'Thai')
        if grades is not None:
            query = query.filter(Inspection.grade.in_(grades))
        query = query.order_by(order_by)
        restaurants = query.all()

        restaurant_results = []
        n = 1
        for r, i in restaurants:
            restaurant_results.append({
                "camis" : r.camis,
                "boro" : r.boro,
                "n" : n,
                "dba": r.dba,
                "address": "%s %s %s" % (r.building, r.street, r.zipcode),
                "phone" : "(%s) %s-%s"  % (r.phone[:3], r.phone[3:6], r.phone[6:10]),
                "score": i.score,
                "grade": i.grade})
            n += 1
        DB_SESSION.commit()
        self.render(
            "index.html",
            restaurant_results=restaurant_results,
            order_request=order_request,
            grade_filter=grades)


if __name__ == "__main__":
    define('host', type=str)
    define('db', type=str)
    define('user', type=str)
    define('pwd', type=str)
    tornado.options.parse_config_file("server.cfg")
    conn_string = 'mysql://%s:%s@%s/%s' % (options.user, options.pwd, options.host, options.db)
    static_path = os.path.join(os.path.dirname(__file__), "static")
    engine = create_engine(conn_string, pool_recycle=3600, echo=False)
    DB_SESSION = sessionmaker(bind=engine)()

    app = tornado.web.Application(
        [
            (r"/inspection", InspectionHandler),
            (r"/", ThaiTimeHandler),
            (r'/static/(.*)', tornado.web.StaticFileHandler, {'path': static_path}),
        ],
        template_path=os.path.join(os.path.dirname(__file__), "templates"),
        static_path=os.path.join(os.path.dirname(__file__), "static"))

    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()