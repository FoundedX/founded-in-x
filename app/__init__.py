'''
This file initializes your application and brings together all of the various
components.
'''

import os, requests, json

from flask import Flask, url_for, redirect, render_template, request
from flask.ext import admin, login
from flask.ext.sqlalchemy import SQLAlchemy

from flask_debugtoolbar import DebugToolbarExtension

from werkzeug.contrib.fixers import ProxyFix
from werkzeug.routing import BaseConverter

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from .models import db, User, Company, Pair
from .views import AdminIndexView, CompanyView

"""
If we set instance_relative_config=True when we create our app with the Flask()
call, app.config.from_pyfile() will load the specified file from the
instance/config.py
"""
app = Flask(__name__)#, instance_relative_config=True)
app.config.from_object('config')
#app.config.from_pyfile('config.py')

toolbar = DebugToolbarExtension(app)
app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False

app.wsgi_app = ProxyFix(app.wsgi_app)

db.app = app
db.init_app(app)


# Initialize flask-login
def init_login():
    login_manager = login.LoginManager()
    login_manager.init_app(app)

    # Create user loader function
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.query(User).get(user_id)


# Flask views
@app.route('/')
def index():
    entries = Company.query.\
                    with_entities(Company.name, Company.url, Company.logo).\
                    filter_by(status='accepted').\
                    order_by(Company.name).all()
    companies = [dict(name=row[0], url=row[1], logo=row[2]) for row in entries]
    
    print entries
    return render_template('index.html', companies=companies)


@app.route('/about')
def about():
    return render_template('about.html')


# Google WebMaster Tools verification page
@app.route("/google25e87b64455912d9.html")
def site_verification():
    """Returns site verification content"""
    return app.send_static_file("site_verification.html")


# Robots file
@app.route("/robots.txt")
def robots_txt():
    return app.send_static_file("robots.txt")


def has_key(d, key):
    if key not in d:
        return None
    return d[key]


class TypeformAPI:
    def __init__(self):
        self.fields = {}
            
            
    def get_data(self):
        last_date = Pair.query.with_entities(Pair.val).filter_by(key='since').one()
        since = last_date[0]

        typeform_url = 'https://api.typeform.com/v0/form/' + app.config['TYPEFORM_FORM_UID']
        payload = {
            'key': app.config['TYPEFORM_API_KEY'],
            'completed': 'true',
            'since' : since
        }

        r = requests.get(typeform_url, params=payload)
        json_data = json.loads(r.text)
        self.questions = json_data['questions']
        self.responses = json_data['responses']
        
    
    def set_fields(self):
        for question in self.questions:
            if question['question'] == 'Startup name':
                self.fields['name'] = question['id']
            elif question['question'] == 'Year founded':
                self.fields['year'] = question['id']
            elif question['question'] == 'Web address':
                self.fields['web_address'] = question['id']
            elif question['question'] == 'Twitter handle':
                self.fields['twitter'] = question['id']
            elif question['question'] == 'URL to high-resolution (white) logo':
                self.fields['url_logo'] = question['id']
            elif question['question'] == 'Contact person':
                self.fields['contact_name'] = question['id']
            elif question['question'] == 'Contact email address':
                self.fields['contact_email'] = question['id']
        
    def update_db(self):
        if len(self.responses) == 0: return
        
        import datetime
        from datetime import timedelta
        import time

        for response in self.responses:
            date_land = response['metadata']['date_land']
            date_submit = datetime.datetime.strptime(date_land, "%Y-%m-%d %H:%M:%S")

            #print response
            # get company details
            name = has_key(response['answers'], self.fields['name'])
            url = has_key(response['answers'], self.fields['web_address'])
            url_to_logo = has_key(response['answers'], self.fields['url_logo'])
            founded_year = has_key(response['answers'], self.fields['year'])
            twitter = has_key(response['answers'], self.fields['twitter'])
            contact_name = has_key(response['answers'], self.fields['contact_name'])
            contact_email = has_key(response['answers'], self.fields['contact_email'])

            bitly_url = ''
            founders = ''
            description = ''

            status = "pending"

            # create a new Company entry in the database
            company = Company(name=name,
                               url=url,
                               logo_submited=url_to_logo,
                               contact_email=contact_email,
                               contact_name = contact_name,
                               twitter = twitter,
                               founded_year = founded_year,
                               date_submit = date_submit,
                               status=status)
            # Add company to database
            db.session.add(company)

        # know there is another last date
        since = time.mktime((date_submit + timedelta(hours=2)).timetuple())
        last_date = Pair.query.with_entities(Pair.val).filter_by(key='since').update({'val': since})

        db.session.commit()


@app.route("/data", methods=['GET'])
def get_companies():
    tf = TypeformAPI()
    tf.get_data()
    tf.update_db()
    return json.dumps(tf.responses)


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(401)
def not_authorized(e):
    return render_template('401.html'), 401

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

@app.errorhandler(410)
def gone(e):
    return render_template('410.html'), 410

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


# Initialize flask-login
init_login()

# Create admin
admin = admin.Admin(app, 'Admin', index_view=AdminIndexView(), base_template='layout.html')

# Add view
admin.add_view(CompanyView(Company, db.session, name='Companies', url='/companies'))
