import flask
from flask import Flask, request, render_template, redirect, url_for
import mysql.connector
import flask_login
import datetime
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ['FLASK_SECRET_KEY']

DB_USER     = os.environ['MYSQL_USER']
DB_PASSWORD = os.environ['MYSQL_PASSWORD']
DB_NAME     = os.environ.get('MYSQL_DATABASE', 'versus')
DB_HOST     = os.environ.get('MYSQL_HOST', 'localhost')

def get_conn():
	return mysql.connector.connect(
		host=DB_HOST,
		user=DB_USER,
		password=DB_PASSWORD,
		database=DB_NAME,
		autocommit=False,
	)

conn = get_conn()


# begin code used for login
login_manager = flask_login.LoginManager()
login_manager.init_app(app)


def getUserList():
	cursor = conn.cursor()
	cursor.execute("SELECT username from Users")
	rows = cursor.fetchall()
	cursor.close()
	return rows


class User(flask_login.UserMixin):
	pass


@login_manager.user_loader
def user_loader(username):
	users = getUserList()
	if not(username) or username not in str(users):
		return
	user = User()
	user.id = username
	return user


@login_manager.request_loader
def request_loader(request):
	users = getUserList()
	username = request.form.get('username')
	if not(username) or username not in str(users):
		return
	user = User()
	user.id = username
	cursor = conn.cursor()
	cursor.execute("SELECT password FROM Users WHERE username = '{0}'".format(username))
	data = cursor.fetchall()
	cursor.close()
	pwd = str(data[0][0])
	user.is_authenticated = check_password_hash(pwd, request.form['password'])


'''
A new page looks like this:
@app.route('new_page_name')
def new_page_function():
	return new_page_html
'''

@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'GET':
		return '''
			<form action='login' method='POST'>
				<input type='text' name='username' id='username' placeholder='username' />
				<input type='password' name='password' id='password' placeholder='password' />
				<input type='submit' name='submit' />
			</form><br />
			<a href='/'>Home</a>
		'''
	# The request method is POST (page is receiving data)
	username = request.form['username']
	cursor = conn.cursor()
	# check if username is registered
	cursor.execute("SELECT user_id, password FROM Users WHERE username = '{0}'".format(username))
	data = cursor.fetchall()
	cursor.close()
	if data:
		pwd = str(data[0][1])
		if check_password_hash(pwd, request.form['password']): 
			flask.session['user_id'] = data[0][0]
			user = User()
			user.id = username
			flask_login.login_user(user)
			return redirect(url_for('home'))
	# information did not match
	return "<a href='/login'>Try again</a><br />\
			<a href='/register'>or make an account</a>"


@login_manager.unauthorized_handler
def unauthorized_handler():
	return render_template('unauth.html')


# you can specify specific methods (GET/POST) in the function header instead
# of inside the function body
@app.route("/register", methods=['GET'])
def register():
	return render_template('register.html')


@app.route("/register", methods=['POST'])
def register_user():
	try:
		username = request.form.get('username')
		email    = request.form.get('email')
		password = request.form.get('password')
		bio      = request.form.get('bio')
	except:
		print("couldn't find all tokens")
		return redirect(url_for('register'))
	cursor = conn.cursor()
	if isUsernameUnique(username):
		pw_hash = generate_password_hash(password)
		# store pw_hash in the users table on login
		cursor.execute(
			"INSERT INTO Users (username, email, password, bio) VALUES ('{0}', '{1}', '{2}', '{3}')".format(
				username, email, pw_hash, bio or ""))
		conn.commit()
		cursor.close()
		# log user in
		user = User()
		user.id = username
		flask_login.login_user(user)
		return render_template('hello.html', name=username, message='account created')
	else:
		cursor.close()
		print("username already in use")
		return redirect(url_for('register'))


def isUsernameUnique(username):
	# use this to check if a username has already been registered
	cursor = conn.cursor()
	cursor.execute("SELECT username FROM Users WHERE username = '{0}'".format(username))
	rows = cursor.fetchall()
	cursor.close()
	return len(rows) == 0


def getUserIdFromUsername(username):
	cursor = conn.cursor()
	cursor.execute("SELECT user_id FROM Users WHERE username = '{0}'".format(username))
	row = cursor.fetchone()
	cursor.close()
	return row[0] if row else None


def getUsernameFromUserId(uid):
	cursor = conn.cursor()
	cursor.execute("SELECT username FROM Users WHERE user_id = '{0}'".format(uid))
	row = cursor.fetchone()
	cursor.close()
	return row[0] if row else None

# end login code


# begin bracket creation code
@app.route('/create', methods=['GET', 'POST'])
@flask_login.login_required
def create_bracket():
	if request.method == 'POST':
		uid           = getUserIdFromUsername(flask_login.current_user.id)
		title         = request.form.get('title')
		description   = request.form.get('description')
		entrant_count = int(request.form.get('entrant_count'))
		cursor = conn.cursor()

		# 1. insert the bracket row
		cursor.execute(
			"INSERT INTO Brackets (host_id, title, description, entrant_count) VALUES ('{0}', '{1}', '{2}', '{3}')".format(
				uid, title, description or "", entrant_count))
		cursor.execute("SELECT LAST_INSERT_ID()")
		bracket_id = cursor.fetchone()[0]

		# 2. insert all entrants in seed order
		entrant_ids = []
		for seed in range(1, entrant_count + 1):
			entrant_name = request.form.get('entrant_' + str(seed))
			cursor.execute(
				"INSERT INTO Entrants (bracket_id, seed, name) VALUES ('{0}', '{1}', '{2}')".format(
					bracket_id, seed, entrant_name))
			cursor.execute("SELECT LAST_INSERT_ID()")
			entrant_ids.append(cursor.fetchone()[0])

		# 3. create Round 1 matchups (seed pairs: 1v2, 3v4, ...)
		round_1_slots = entrant_count // 2
		for slot in range(1, round_1_slots + 1):
			a = entrant_ids[(slot - 1) * 2]
			b = entrant_ids[(slot - 1) * 2 + 1]
			cursor.execute(
				"INSERT INTO Matchups (bracket_id, round, slot, entrant_a_id, entrant_b_id) VALUES ('{0}', 1, '{1}', '{2}', '{3}')".format(
					bracket_id, slot, a, b))

		# 4. create empty shells for later rounds
		slots = round_1_slots // 2
		round_num = 2
		while slots >= 1:
			for slot in range(1, slots + 1):
				cursor.execute(
					"INSERT INTO Matchups (bracket_id, round, slot) VALUES ('{0}', '{1}', '{2}')".format(
						bracket_id, round_num, slot))
			slots //= 2
			round_num += 1

		conn.commit()
		cursor.close()
		return redirect(url_for('view_bracket', bracket_id=bracket_id))
	else:
		return render_template('create.html')
# end bracket creation code


# begin browse code
def getAllBrackets():
	cursor = conn.cursor()
	cursor.execute(
		"SELECT b.bracket_id, b.title, b.status, b.entrant_count, b.created_at, u.username "
		"FROM Brackets b JOIN Users u ON b.host_id = u.user_id "
		"ORDER BY b.created_at DESC")
	rows = cursor.fetchall()
	cursor.close()
	return rows


@app.route('/browse', methods=['GET'])
def browse():
	brackets = getAllBrackets()
	return render_template('browse.html', brackets=brackets)
# end browse code


# begin bracket view code
def getBracketInfo(bracket_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT b.bracket_id, b.title, b.description, b.status, b.entrant_count, u.username "
		"FROM Brackets b JOIN Users u ON b.host_id = u.user_id "
		"WHERE b.bracket_id = '{0}'".format(bracket_id))
	row = cursor.fetchone()
	cursor.close()
	return row


def getMatchupsForBracket(bracket_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT m.matchup_id, m.round, m.slot, ea.name, eb.name, ew.name, m.votes_a, m.votes_b "
		"FROM Matchups m "
		"LEFT JOIN Entrants ea ON ea.entrant_id = m.entrant_a_id "
		"LEFT JOIN Entrants eb ON eb.entrant_id = m.entrant_b_id "
		"LEFT JOIN Entrants ew ON ew.entrant_id = m.winner_entrant_id "
		"WHERE m.bracket_id = '{0}' "
		"ORDER BY m.round, m.slot".format(bracket_id))
	rows = cursor.fetchall()
	cursor.close()
	return rows


# start of predictions code
# 1: get round1 matchups
def getRoundOneMatchups(bracket_id):
	# Left Join would work too, yet, 
	# since we shouldn't have null entries anyways regular join is also fine.
	# it is a semantic choice.
	cursor = conn.cursor()
	cursor.execute(
		"SELECT m.matchup_id,ea.entrant_id, ea.name, eb.entrant_id, eb.name "
		"FROM Matchups m "
		"JOIN Entrants ea ON ea.entrant_id = m.entrant_a_id "
		"JOIN Entrants eb ON eb.entrant_id = m.entrant_b_id "
		"WHERE m.bracket_id = '{0}' AND m.round = 1 "
		"ORDER BY m.slot".format(bracket_id))
	
	rows = cursor.fetchall()
	cursor.close()
	return rows

@app.route('/predict<bracket_id>', methods=['POST'])
@flask_login.login_required
def submit_predictions(bracket_id):
	uid           = getUserIdFromUsername(flask_login.current_user.id) 
	r1 = getRoundOneMatchups(bracket_id)
	submitted_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	cursor = conn.cursor()
	for m in r1:
		matchup_id = m[0]
		pick = request.form.get('pick_' + str(matchup_id))
		cursor.execute(
			"INSERT INTO Predictions (user_id, matchup_id, entrant_id, submitted_at) "
			"VALUES ('{0}', '{1}', '{2}', '{3}')".format(uid, matchup_id, pick, submitted_at))
	conn.commit()
	cursor.close()
	return redirect(url_for('view_bracket', bracket_id=bracket_id))

# END OF PREDICTION CODE


# START OF VOTING CODE
def getCurrentRound(bracket_id):
	cursor = conn.cursor()
	cursor.execute("SELECT status FROM Brackets WHERE bracket_id = '{0}'".format(bracket_id))
	row = cursor.fetchone()
	cursor.close()
	status = row[0]
	if 'round_' not in status:
		return None
	return int(status[-1])

def getCurrentRoundMatchups(bracket_id):
	round = getCurrentRound(bracket_id)
	if round is None:
		return []
	cursor = conn.cursor()
	cursor.execute(
		"SELECT m.matchup_id,ea.entrant_id, ea.name, eb.entrant_id, eb.name "
		"FROM Matchups m "
		"JOIN Entrants ea ON ea.entrant_id = m.entrant_a_id "
		"JOIN Entrants eb ON eb.entrant_id = m.entrant_b_id "
		"WHERE m.bracket_id = '{0}' AND m.round = {1} "
		"ORDER BY m.slot".format(bracket_id, round))
	rows = cursor.fetchall()
	cursor.close()
	return rows


@app.route('/vote<bracket_id>', methods=['POST'])
@flask_login.login_required
def submit_votes(bracket_id):
	uid           = getUserIdFromUsername(flask_login.current_user.id)
	cr            = getCurrentRoundMatchups(bracket_id)
	cursor = conn.cursor()
	for m in cr:
		matchup_id = m[0]
		entrant_a_id = m[1]
		vote = request.form.get('vote_' + str(matchup_id)) ###
		cursor.execute(
			"INSERT INTO Votes (user_id, matchup_id, entrant_id) "
			"VALUES ('{0}', '{1}', '{2}')".format(uid, matchup_id, vote))
		if vote == str(entrant_a_id):
			cursor.execute(
				"UPDATE Matchups SET votes_a = votes_a + 1 WHERE matchup_id = '{0}'".format(matchup_id)
			)
		else: 
			cursor.execute(
				"UPDATE Matchups SET votes_b = votes_b + 1 WHERE matchup_id = '{0}'".format(matchup_id)
			)
	conn.commit()
	cursor.close()
	return redirect(url_for('view_bracket', bracket_id = bracket_id))
		
		
# END OF VOTING CODE

# START OF FOLLOWS CODE

def getFollowers(user_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT u.username FROM Follows f "
		"JOIN Users u ON f.follower_id = u.user_id "
		"WHERE f.followed_id = '{0}'".format(user_id)
	)
	rows = cursor.fetchall()
	cursor.close()
	return rows

def getFollowing(user_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT u.username FROM Follows f "
		"JOIN Users u ON f.followed_id = u.user_id "
		"WHERE f.follower_id = '{0}'".format(user_id)
	)
	rows = cursor.fetchall()
	cursor.close()
	return rows

@app.route("/follow<username>", methods = ['POST'])
@flask_login.login_required
def follow_user(username):
	follower_id = getUserIdFromUsername(flask_login.current_user.id)
	followed_id = getUserIdFromUsername(username)
	cursor = conn.cursor()
	cursor.execute(
		"INSERT INTO Follows (follower_id, followed_id) VALUES ('{0}', '{1}')".format(follower_id, followed_id)
	)
	conn.commit()
	cursor.close()
	return redirect(url_for('view_profile', username=username))

@app.route("/unfollow<username>", methods = ['POST'])
@flask_login.login_required
def unfollow_user(username):
	follower_id = getUserIdFromUsername(flask_login.current_user.id)
	followed_id = getUserIdFromUsername(username)
	cursor = conn.cursor()
	cursor.execute(
		"DELETE FROM Follows WHERE follower_id = '{0}' AND followed_id = '{1}'".format(follower_id, followed_id)
	)
	conn.commit()
	cursor.close()
	return redirect(url_for('view_profile', username = username))


# END OF FOLLOWS CODE


# START OF COMMENTS CODE

def getCommentsForBracket(bracket_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT c.matchup_id, u.username, c.body "
		"FROM Comments c "
		"JOIN Users u ON c.user_id = u.user_id "
		"JOIN Matchups m ON c.matchup_id = m.matchup_id "
		"WHERE m.bracket_id = '{0}'".format(bracket_id))
	rows = cursor.fetchall()
	cursor.close()
	return rows

@app.route("/comment<matchup_id>", methods = ['POST'])
@flask_login.login_required
def post_comment(matchup_id):
	uid = getUserIdFromUsername(flask_login.current_user.id)
	body = request.form.get('body')
	cursor = conn.cursor()
	cursor.execute(
		"INSERT INTO Comments (user_id, matchup_id, body) "
		"VALUES ('{0}', '{1}', '{2}')".format(uid, matchup_id, body))
	cursor.execute("SELECT bracket_id FROM Matchups WHERE matchup_id = '{0}'".format(matchup_id))
	row = cursor.fetchone()
	bracket_id = row[0]
	conn.commit()
	cursor.close()
	return redirect(url_for('view_bracket', bracket_id = bracket_id))

# END OF COMMENTS CODE




# START LEADERBOARD CODE
def getLeaderboard():
	cursor = conn.cursor()
	cursor.execute("""
		SELECT
				username, 
				total_points,
				RANK() OVER (ORDER BY total_points DESC),
				DENSE_RANK() OVER (ORDER BY total_points DESC),
				PERCENT_RANK() OVER (ORDER BY total_points DESC)
		FROM (
			SELECT
				u.username,
				SUM(p.points_earned) AS total_points
			FROM Users u
			JOIN Predictions p ON p.user_id = u.user_id
			GROUP BY u.user_id, u.username
			) AS t
			ORDER BY total_points DESC
	""")
	rows = cursor.fetchall()
	cursor.close()
	return rows

@app.route('/leaderboard', methods = ['GET'])
def leaderboard():
		rows = getLeaderboard()
		try:
			me = flask_login.current_user.id
		except AttributeError:
			me = None  # not logged in

		return render_template('leaderboard.html', rows=rows, me=me)

# END LEADERBOARD CODE


# START CHAMPION PATH CODE
def getChampionPath(bracket_id):
	cursor = conn.cursor()
	cursor.execute("""
	WITH RECURSIVE champ_path AS (
				SELECT m.matchup_id, m.round, m.slot, m.winner_entrant_id
				FROM Matchups m
				WHERE m.bracket_id = '{0}'
					and m.round = (
						SELECT MAX(round) 
						FROM Matchups WHERE bracket_id = '{0}' )
				
				UNION ALL

				SELECT m.matchup_id, m.round, m.slot, m.winner_entrant_id
				FROM Matchups m
				JOIN champ_path cp
				ON m.bracket_id = '{0}'
				AND m.round = cp.round - 1
				AND m.slot IN (cp.slot * 2 - 1, cp.slot * 2)
				AND m.winner_entrant_id = cp.winner_entrant_id
				)

				SELECT cp.round, ea.name, eb.name, ew.name
				FROM champ_path cp
				JOIN Matchups m ON m.matchup_id = cp.matchup_id
				JOIN Entrants ea ON ea.entrant_id = m.entrant_a_id
				JOIN Entrants eb ON eb.entrant_id = m.entrant_b_id
				JOIN Entrants ew ON ew.entrant_id = m.winner_entrant_id
				ORDER BY cp.round
	""".format(bracket_id))
	rows = cursor.fetchall()
	cursor.close()
	return rows

@app.route('/champion<bracket_id>', methods = ['GET'])
def champion_path(bracket_id):
	path = getChampionPath(bracket_id)
	return render_template('champion.html', path=path)
# END CHAMPION PATH CODE



@app.route('/bracket<bracket_id>', methods=['GET'])
def view_bracket(bracket_id):
	bracket  = getBracketInfo(bracket_id)
	matchups = getMatchupsForBracket(bracket_id)
	r1_matchups = getRoundOneMatchups(bracket_id)
	comments = getCommentsForBracket(bracket_id)
	cr_matchups = getCurrentRoundMatchups(bracket_id)
	return render_template('bracket.html', bracket=bracket, matchups=matchups, r1_matchups=r1_matchups, comments=comments, cr_matchups=cr_matchups)
# end bracket view code

# START CODE FOR PROFILE PAGE 

def getBio(user_id):
	# gets user_id, returns bio string
	cursor = conn.cursor()
	cursor.execute("SELECT bio FROM Users WHERE user_id = '{0}'".format(user_id))
	row = cursor.fetchone()
	cursor.close()
	return row[0] if row else None

def getProfileStats(user_id):
	# gets user_id, returns (total_points, prediction_count, correct_count)
	cursor = conn.cursor()
	cursor.execute(
	"SELECT COALESCE(SUM(points_earned), 0), COUNT(*), COALESCE(SUM(is_correct), 0) "
	"FROM Predictions WHERE user_id = '{0}'".format(user_id))
	row = cursor.fetchone()
	cursor.close()
	return row

def getAchievements(user_id):
	# gets user_id, returns list of (code, name)
	cursor = conn.cursor()
	cursor.execute(
		"SELECT ua.code, a.name "
		"FROM user_achievements ua JOIN Achievements a ON ua.code = a.code "
		"WHERE ua.user_id = '{0}'".format(user_id))
	rows = cursor.fetchall()
	cursor.close()
	return rows

def getHostedBrackets(user_id):
	# gets user_id, returns list of (bracket_id, title, status)
	cursor = conn.cursor()
	cursor.execute(
		"SELECT bracket_id, title, status "
		"FROM Brackets WHERE host_id = '{0}'".format(user_id))
	rows = cursor.fetchall()
	cursor.close()
	return rows

@app.route('/user<username>', methods=['GET'])
def view_profile(username):
	uid          = getUserIdFromUsername(username)
	bio          = getBio(uid)
	stats        = getProfileStats(uid)
	achievements = getAchievements(uid)
	hosted       = getHostedBrackets(uid)
	followers    = getFollowers(uid)
	following    = getFollowing(uid)
	return render_template('profile.html', username=username, bio=bio, stats=stats, achievements=achievements, hosted=hosted, followers=followers, following=following)

# END CODE FOR PROFILE PAGE


# START OF HOST CONTROL CODE
@app.route('/open<bracket_id>', methods=['POST'])
@flask_login.login_required
def open_round_one(bracket_id):
	cursor = conn.cursor()
	try:
		uid = getUserIdFromUsername(flask_login.current_user.id)
		cursor.execute(
			"SELECT host_id, status FROM Brackets WHERE bracket_id = %s FOR UPDATE",
			(bracket_id,),
		)
		bracket = cursor.fetchone()
		if bracket is None:
			conn.rollback()
			flask.abort(404)
		if bracket[0] != uid:
			conn.rollback()
			flask.abort(403)
		if bracket[1] != 'predictions_open':
			conn.rollback()
			flask.abort(409)

		cursor.execute(
			"UPDATE Brackets SET status = 'round_1' WHERE bracket_id = %s",
			(bracket_id,),
		)
		conn.commit()
	except mysql.connector.Error:
		conn.rollback()
		raise
	finally:
		cursor.close()
	return redirect(url_for('view_bracket', bracket_id=bracket_id))		

@app.route('/close<bracket_id>', methods=['POST'])
@flask_login.login_required
def close_current_round(bracket_id):
	cursor = conn.cursor()
	try:
		uid = getUserIdFromUsername(flask_login.current_user.id)
		cursor.execute(
			"SELECT host_id, status FROM Brackets WHERE bracket_id = %s FOR UPDATE",
			(bracket_id,),
		)
		bracket = cursor.fetchone()
		if bracket is None:
			conn.rollback()
			flask.abort(404)
		if bracket[0] != uid:
			conn.rollback()
			flask.abort(403)

		status = bracket[1]
		if not status.startswith('round_'):
			conn.rollback()
			flask.abort(409)
		current_round = int(status.removeprefix('round_'))

		cursor.callproc('close_round', (bracket_id, current_round))
		conn.commit()
	except mysql.connector.Error:
		conn.rollback()
		raise
	finally:
		cursor.close()
	return redirect(url_for('view_bracket', bracket_id=bracket_id))			

# END OF HOST CONTROL CODE

# START OF ADMIN CODE
@app.route('/admin', methods=['GET', 'POST'])
@flask_login.login_required
def admin():
	if flask_login.current_user.id != 'admin':
		return render_template('unauth.html')
	query = None
	columns = None
	rows = None
	error = None
	if request.method == 'POST' :
		query = request.form.get('query')
		cursor = conn.cursor()
		try: 
			cursor.execute(query)
			if cursor.description:
				columns = [d[0] for d in cursor.description]
				rows = cursor.fetchall()
			conn.commit()
		except Exception as e:
			error = str(e)
		cursor.close()
	return render_template('admin.html', query=query, columns=columns, rows=rows, error=error)

# END OF ADMIN CODE

# default page
@app.route('/', methods=['GET', 'POST'])
def home():
	if request.method == 'POST':
		flask_login.logout_user()
	try:
		username = flask_login.current_user.id
		return render_template('hello.html', name=username, message='welcome to VERSUS')
	except AttributeError:  # not logged in
		return render_template('hello.html', message=None)


if __name__ == "__main__":
	debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
	port = int(os.environ.get('PORT', '5001'))
	app.run(port=port, debug=debug)
