""" ORM models need for our DOH app"""

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Date, Integer, String, Text

Base = declarative_base()

class Restaurant(Base):
    """ DB model representing a restaurant """

    __tablename__ = 'restaurant'

    restaurant_id = Column(Integer, primary_key=True)
    camis = Column(Integer)
    dba = Column(String(255))
    boro = Column(String(25))
    building = Column(String(25))
    street = Column(String(255))
    zipcode = Column(Integer)
    phone = Column(String(10))
    cuisine = Column(String(100))
    last_inspection_date = Column(Date)

class Inspection(Base):
    """ DB model representing an individual inspection associated with a restaurant """

    __tablename__ = 'inspection'

    inspection_id = Column(Integer, primary_key=True)
    camis = Column(Integer)
    inspection_date = Column(Date())
    action = Column(String(255))
    score = Column(Integer)
    grade = Column(String(15))
    grade_date = Column(Date())
    inspection_type = Column(String(255))

class Violation(Base):
    """ DB model representing an individual violation associated with an inspection """

    __tablename__ = 'violation'

    violation_id = Column(Integer, primary_key=True)
    camis = Column(Integer)
    inspection_date = Column(Date())
    violation_code = Column(String(11))
    violation_description = Column(Text)
    critical_flag = Column(String(25))