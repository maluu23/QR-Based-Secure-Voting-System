from flask import Flask, render_template, request, redirect, url_for, flash
from flask import session
from flask_mysqldb import MySQL
from flask_mail import Mail, Message
import qrcode
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True

app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")


mail = Mail(app)
def generate_qr(token):

    folder = "static/qrcodes"

    if not os.path.exists(folder):
        os.makedirs(folder)

    filename = f"{token}.png"

    filepath = os.path.join(folder, filename)

    qr_url = f"http://10.34.54.252:5000/verify-qr/{token}"

    img = qrcode.make(qr_url)

    img.save(filepath)

    return filename
def send_qr_email(student_email, student_name, qr_image):

    try:

        print("Sending email to:", student_email)

        msg = Message(
            "Department Election - Your QR Code",
            sender=app.config["MAIL_USERNAME"],
            recipients=[student_email]
        )

        msg.body = f"""
           Hello {student_name},

           Your Department Election has started.

           Please use the attached QR Code to cast your vote.

           Instructions:

              1. Open the attached QR Code.
              2. Scan it using your phone camera or Google Lens.
              3. The voting page will open automatically.
              4. Cast your vote.
              5. You can vote only once.

            Thank you.

            Department Election Committee
          """
        with app.open_resource("static/qrcodes/" + qr_image) as fp:
            msg.attach(
                qr_image,
                "image/png",
                fp.read()
            )

        mail.send(msg)

        print("✅ Email Sent Successfully")

    except Exception as e:

        print("❌ Email Error:", e)
        
app.secret_key = "smartvoting123"

# MySQL Configuration
app.config["MYSQL_HOST"] = "localhost"
app.config["MYSQL_USER"] = "root"
app.config["MYSQL_PASSWORD"] = "malinis"
app.config["MYSQL_DB"] = "department_election"

mysql = MySQL(app)

# Home Page
@app.route("/")
def home():
    return render_template("index.html")

# Admin Login Page
@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        cursor = mysql.connection.cursor()

        cursor.execute(
            "SELECT * FROM admin WHERE username=%s AND password=%s",
            (username, password)
        )

        admin = cursor.fetchone()

        cursor.close()

        if admin:
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid Username or Password", "danger")

    return render_template("admin_login.html")

@app.route("/admin-dashboard")
def admin_dashboard():

    cursor = mysql.connection.cursor()

    # Total Students
    cursor.execute("SELECT COUNT(*) FROM students")
    total_students = cursor.fetchone()[0]

    # Total Candidates
    cursor.execute("SELECT COUNT(*) FROM candidates")
    total_candidates = cursor.fetchone()[0]

    # Total Elections
    cursor.execute("SELECT COUNT(*) FROM elections")
    total_elections = cursor.fetchone()[0]

    # Total Votes
    cursor.execute("SELECT COUNT(*) FROM votes")
    total_votes = cursor.fetchone()[0]

    cursor.close()

    return render_template(
        "admin_dashboard.html",
        total_students=total_students,
        total_candidates=total_candidates,
        total_elections=total_elections,
        total_votes=total_votes
    )

@app.route("/add-student", methods=["GET", "POST"])
def add_student():

    if request.method == "POST":

        register_no = request.form["register_no"]
        student_name = request.form["student_name"]
        email = request.form["email"]
        phone = request.form["phone"]
        department = request.form["department"]
        year = request.form["year"]
        password = request.form["password"]

        cursor = mysql.connection.cursor()

        # Check Duplicate Register Number
        cursor.execute(
            "SELECT * FROM students WHERE register_no=%s",
            (register_no,)
        )

        existing_student = cursor.fetchone()

        if existing_student:

            cursor.close()

            flash("Register Number already exists!", "danger")

            return redirect(url_for("add_student"))

        # Generate QR
        qr_token = str(uuid.uuid4())

        qr_image = generate_qr(qr_token)

        # Insert Student
        cursor.execute("""
        INSERT INTO students
        (register_no, student_name, email, phone, department, year, password, qr_token)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            register_no,
            student_name,
            email,
            phone,
            department,
            year,
            password,
            qr_token
        ))

        mysql.connection.commit()

        # send_qr_email(email, student_name, qr_image)

        cursor.close()

        flash("Student Added Successfully!", "success")

        return redirect(url_for("add_student"))

    return render_template("add_student.html")
@app.route("/verify-qr/<token>")
def verify_qr(token):

    cursor = mysql.connection.cursor()

    # Check active election
    cursor.execute("""
        SELECT election_id
        FROM elections
        WHERE status='Active'
        LIMIT 1
    """)

    election = cursor.fetchone()

    if election is None:

        cursor.close()

        return """
        <h2 style='color:red;text-align:center;margin-top:50px;'>
        Election has not started yet.
        </h2>
        """

    # Check student QR
    cursor.execute("""
        SELECT
            student_id,
            student_name,
            has_voted
        FROM students
        WHERE qr_token=%s
    """, (token,))

    student = cursor.fetchone()

    cursor.close()

    if student is None:
        return "<h2>Invalid QR Code</h2>"

    if student[2] == 1:
        return "<h2>You have already voted.</h2>"

    session["student_id"] = student[0]
    session["election_id"] = election[0]

    return redirect(url_for("vote"))
@app.route("/vote")
def vote():

    if "student_id" not in session:
        return "<h2>Access Denied</h2>"

    cursor = mysql.connection.cursor()

    # Get active election
    cursor.execute("""
        SELECT election_id
        FROM elections
        WHERE status='Active'
        LIMIT 1
    """)

    election = cursor.fetchone()

    if election is None:

        cursor.close()

        return """
        <h2 style="color:red;text-align:center;margin-top:50px;">
            Election has not started yet.
        </h2>
        """

    # Store election ID in session
    session["election_id"] = election[0]

    # Posts
    cursor.execute("""
        SELECT post_id, post_name
        FROM posts
        ORDER BY display_order
    """)

    posts = cursor.fetchall()

    # Approved Candidates
    cursor.execute("""
        SELECT
            c.candidate_id,
            s.student_name,
            c.student_id,
            c.post_id,
            c.manifesto
        FROM candidates c
        JOIN students s
            ON c.student_id = s.student_id
        WHERE c.approval_status='Approved'
        ORDER BY c.post_id
    """)

    candidates = cursor.fetchall()

    cursor.close()

    return render_template(
        "vote.html",
        posts=posts,
        candidates=candidates
    )
@app.route("/submit-vote", methods=["POST"])
def submit_vote():

    # Check student login / QR verification
    if "student_id" not in session:
        return "Access Denied"

    student_id = session["student_id"]

    cursor = mysql.connection.cursor()

    # -----------------------------------
    # GET ACTIVE ELECTION
    # -----------------------------------

    cursor.execute("""
        SELECT election_id
        FROM elections
        WHERE status='Active'
        LIMIT 1
    """)

    election = cursor.fetchone()

    if election is None:

        cursor.close()

        return """
        <h2 style="color:red;text-align:center;margin-top:50px;">
            Election has not started yet.
        </h2>
        """

    # Get election ID directly from database
    election_id = election[0]


    # -----------------------------------
    # CHECK STUDENT
    # -----------------------------------

    cursor.execute("""
        SELECT has_voted
        FROM students
        WHERE student_id=%s
    """, (student_id,))

    student_status = cursor.fetchone()

    if student_status is None:

        cursor.close()

        return """
        <h2 style="color:red;text-align:center;margin-top:50px;">
            Student not found.
        </h2>
        """


    # -----------------------------------
    # DUPLICATE VOTE CHECK
    # -----------------------------------

    if student_status[0] == 1:

        cursor.close()

        return """
        <h2 style="color:red;text-align:center;margin-top:50px;">
            You have already voted.
        </h2>
        """


    # -----------------------------------
    # GET ALL POSTS
    # -----------------------------------

    cursor.execute("""
        SELECT post_id
        FROM posts
        ORDER BY display_order
    """)

    posts = cursor.fetchall()


    vote_count = 0


    # -----------------------------------
    # SAVE VOTES
    # -----------------------------------

    for post in posts:

        post_id = post[0]

        candidate = request.form.get(
            f"post_{post_id}"
        )

        if candidate:

            cursor.execute("""
                INSERT INTO votes
                (
                    election_id,
                    voter_id,
                    candidate_id,
                    post_id
                )
                VALUES
                (%s,%s,%s,%s)
            """,
            (
                election_id,
                student_id,
                candidate,
                post_id
            ))

            vote_count += 1


    # -----------------------------------
    # CHECK WHETHER VOTE WAS SELECTED
    # -----------------------------------

    if vote_count == 0:

        cursor.close()

        return """
        <h2 style="color:red;text-align:center;margin-top:50px;">
            Please select at least one candidate.
        </h2>
        """


    # -----------------------------------
    # MARK STUDENT AS VOTED
    # -----------------------------------

    cursor.execute("""
        UPDATE students
        SET has_voted=1
        WHERE student_id=%s
    """, (student_id,))


    # -----------------------------------
    # COMMIT
    # -----------------------------------

    mysql.connection.commit()

    cursor.close()


    # -----------------------------------
    # CLEAR SESSION
    # -----------------------------------

    session.clear()


    # -----------------------------------
    # SUCCESS MESSAGE
    # -----------------------------------

    return """
    <!DOCTYPE html>

    <html>

    <head>

        <title>Vote Submitted</title>

        <style>

            body {
                font-family: Arial, sans-serif;
                background: #f4f6f9;
                text-align: center;
                padding-top: 100px;
            }

            .box {
                background: white;
                width: 500px;
                max-width: 90%;
                margin: auto;
                padding: 40px;
                border-radius: 15px;
                box-shadow: 0 5px 20px rgba(0,0,0,0.15);
            }

            h1 {
                color: #198754;
            }

            p {
                font-size: 18px;
                color: #555;
            }

        </style>

    </head>

    <body>

        <div class="box">

            <h1>
                ✅ Vote Submitted Successfully!
            </h1>

            <p>
                Thank you for participating in the election.
            </p>

            <p>
                Your vote has been recorded securely.
            </p>

        </div>

    </body>

    </html>
    """
@app.route("/view-students")
def view_students():

    cursor = mysql.connection.cursor()

    cursor.execute("""
    SELECT
        student_id,
        register_no,
        student_name,
        email,
        phone,
        department,
        year
    FROM students
    ORDER BY CAST(register_no AS UNSIGNED) ASC
    """)

    students = cursor.fetchall()

    cursor.close()

    return render_template("view_students.html", students=students)

@app.route("/edit-student/<int:id>", methods=["GET", "POST"])
def edit_student(id):

    cursor = mysql.connection.cursor()

    if request.method == "POST":

        register_no = request.form["register_no"]
        student_name = request.form["student_name"]
        email = request.form["email"]
        phone = request.form["phone"]
        department = request.form["department"]
        year = request.form["year"]

        cursor.execute("""
        UPDATE students
        SET register_no=%s,
            student_name=%s,
            email=%s,
            phone=%s,
            department=%s,
            year=%s
        WHERE student_id=%s
        """,
        (register_no, student_name, email, phone, department, year, id))

        mysql.connection.commit()

        cursor.close()

        flash("Student Updated Successfully!", "success")

        return redirect(url_for("view_students"))

    cursor.execute("SELECT * FROM students WHERE student_id=%s", (id,))
    student = cursor.fetchone()

    cursor.close()

    return render_template("edit_student.html", student=student)

@app.route("/delete-student/<int:id>")
def delete_student(id):

    cursor = mysql.connection.cursor()

    cursor.execute("DELETE FROM students WHERE student_id=%s", (id,))

    mysql.connection.commit()

    cursor.close()

    flash("Student Deleted Successfully!", "success")

    return redirect(url_for("view_students"))

@app.route("/add-candidate", methods=["GET", "POST"])
def add_candidate():

    cursor = mysql.connection.cursor()

    # Get all students
    cursor.execute("""
        SELECT student_id, student_name, register_no
        FROM students
        WHERE is_active = 1
        ORDER BY student_name
    """)
    students = cursor.fetchall()

    # Get all posts
    cursor.execute("""
        SELECT post_id, post_name
        FROM posts
        ORDER BY display_order
    """)
    posts = cursor.fetchall()

    if request.method == "POST":

        student_id = request.form["student_id"]
        post_id = request.form["post_id"]
        manifesto = request.form["manifesto"]

        cursor.execute("""
            INSERT INTO candidates
            (student_id, post_id, manifesto, approval_status)
            VALUES (%s, %s, %s, 'Approved')
        """, (student_id, post_id, manifesto))

        mysql.connection.commit()

        flash("Candidate Added Successfully!", "success")

        cursor.close()

        return redirect(url_for("add_candidate"))

    cursor.close()

    return render_template(
        "add_candidate.html",
        students=students,
        posts=posts
    )
@app.route("/view-candidates")
def view_candidates():

    cursor = mysql.connection.cursor()

    cursor.execute("""
        SELECT
            c.candidate_id,
            s.student_name,
            s.register_no,
            s.department,
            s.year,
            p.post_name,
            c.manifesto,
            c.approval_status

        FROM candidates c

        INNER JOIN students s
            ON c.student_id = s.student_id

        INNER JOIN posts p
            ON c.post_id = p.post_id

        ORDER BY c.candidate_id DESC
    """)

    candidates = cursor.fetchall()

    cursor.close()

    return render_template(
        "view_candidates.html",
        candidates=candidates
    )
@app.route("/edit-candidate/<int:id>", methods=["GET", "POST"])
def edit_candidate(id):

    cursor = mysql.connection.cursor()

    if request.method == "POST":

        post_id = request.form["post_id"]
        manifesto = request.form["manifesto"]
        approval_status = request.form["approval_status"]

        cursor.execute("""
            UPDATE candidates
            SET
                post_id=%s,
                manifesto=%s,
                approval_status=%s
            WHERE candidate_id=%s
        """, (post_id, manifesto, approval_status, id))

        mysql.connection.commit()

        flash("Candidate Updated Successfully!", "success")

        cursor.close()

        return redirect(url_for("view_candidates"))

    # Candidate Details
    cursor.execute("""
        SELECT
            candidate_id,
            student_id,
            post_id,
            manifesto,
            approval_status
        FROM candidates
        WHERE candidate_id=%s
    """, (id,))

    candidate = cursor.fetchone()

    # All Posts
    cursor.execute("""
        SELECT post_id, post_name
        FROM posts
        ORDER BY display_order
    """)

    posts = cursor.fetchall()

    cursor.close()

    return render_template(
        "edit_candidate.html",
        candidate=candidate,
        posts=posts
    )
@app.route("/delete-candidate/<int:id>")
def delete_candidate(id):

    cursor = mysql.connection.cursor()

    cursor.execute(
        "DELETE FROM candidates WHERE candidate_id=%s",
        (id,)
    )

    mysql.connection.commit()

    cursor.close()

    flash("Candidate Deleted Successfully!", "success")

    return redirect(url_for("view_candidates"))

@app.route("/create-election", methods=["GET", "POST"])
def create_election():

    if request.method == "POST":

        election_name = request.form["election_name"]
        academic_year = request.form["academic_year"]
        start_datetime = request.form["start_datetime"]
        end_datetime = request.form["end_datetime"]

        cursor = mysql.connection.cursor()

        cursor.execute("""
            INSERT INTO elections
            (
                election_name,
                academic_year,
                start_datetime,
                end_datetime,
                status
            )
            VALUES
            (
                %s,%s,%s,%s,'Upcoming'
            )
        """,
        (
            election_name,
            academic_year,
            start_datetime,
            end_datetime
        ))

        mysql.connection.commit()

        cursor.close()

        flash("Election Created Successfully!", "success")

        return redirect(url_for("create_election"))

    return render_template("create_election.html")
@app.route("/view-elections")
def view_elections():

    cursor = mysql.connection.cursor()

    cursor.execute("""
        SELECT
        election_id,
        election_name,
        academic_year,
        start_datetime,
        end_datetime,
        status
        FROM elections
        ORDER BY election_id DESC
    """)

    elections = cursor.fetchall()

    cursor.close()

    return render_template(
        "view_elections.html",
        elections=elections
    )
@app.route("/start-election/<int:election_id>")
def start_election(election_id):

    cursor = mysql.connection.cursor()

    # First, make all elections Upcoming/Completed except Active
    cursor.execute("""
        UPDATE elections
        SET status='Upcoming'
        WHERE status='Active'
    """)

    # Start selected election
    cursor.execute("""
        UPDATE elections
        SET status='Active'
        WHERE election_id=%s
    """, (election_id,))

    mysql.connection.commit()

    cursor.close()

    flash("Election Started Successfully!", "success")

    return redirect(url_for("view_elections"))
@app.route("/end-election/<int:election_id>")
def end_election(election_id):

    cursor = mysql.connection.cursor()

    cursor.execute("""
        UPDATE elections
        SET status='Completed'
        WHERE election_id=%s
    """, (election_id,))

    mysql.connection.commit()

    cursor.close()

    flash("Election Completed Successfully!", "success")

    return redirect(url_for("view_elections"))

@app.route("/send-qr")
def send_qr():

    cursor = mysql.connection.cursor()

    # Eligible students
    cursor.execute("""
        SELECT
            student_name,
            email,
            qr_token
        FROM students
        WHERE is_active=1
    """)

    students = cursor.fetchall()

    for student in students:

        student_name = student[0]
        email = student[1]
        token = student[2]

        qr_image = generate_qr(token)

        send_qr_email(
            email,
            student_name,
            qr_image
        )

    cursor.close()

    flash("QR Codes Sent Successfully to All Students!", "success")

    return redirect(url_for("admin_dashboard"))

@app.route("/results")
def results():

    cursor = mysql.connection.cursor()

    # Get all posts
    cursor.execute("""
        SELECT post_id, post_name
        FROM posts
        ORDER BY display_order
    """)

    posts = cursor.fetchall()

    all_results = []

    for post in posts:

        post_id = post[0]
        post_name = post[1]

        # Find winner for each post
        cursor.execute("""
            SELECT
                c.candidate_id,
                s.student_name,
                s.register_no,
                COUNT(v.vote_id) AS total_votes
            FROM candidates c

            JOIN students s
                ON c.student_id = s.student_id

            LEFT JOIN votes v
                ON c.candidate_id = v.candidate_id

            WHERE c.post_id=%s
            AND c.approval_status='Approved'

            GROUP BY
                c.candidate_id,
                s.student_name,
                s.register_no

            ORDER BY total_votes DESC

            LIMIT 1
        """, (post_id,))

        winner = cursor.fetchone()

        all_results.append({
            "post_name": post_name,
            "winner": winner
        })

    cursor.close()

    return render_template(
        "result.html",
        all_results=all_results
    )
@app.route("/winner")
def winner():

    cursor = mysql.connection.cursor()

    cursor.execute("""
        SELECT
            e.election_name,
            e.academic_year,
            p.post_name,
            s.student_name,
            s.register_no,
            COUNT(v.vote_id) AS total_votes
        FROM candidates c

        JOIN students s
            ON c.student_id = s.student_id

        JOIN posts p
            ON c.post_id = p.post_id

        JOIN votes v
            ON c.candidate_id = v.candidate_id

        JOIN elections e
            ON v.election_id = e.election_id

        WHERE c.approval_status='Approved'

        GROUP BY
            e.election_id,
            e.election_name,
            e.academic_year,
            p.post_id,
            p.post_name,
            p.display_order,
            c.candidate_id,
            s.student_name,
            s.register_no

        ORDER BY
            e.election_id DESC,
            p.display_order,
            total_votes DESC
    """)

    rows = cursor.fetchall()

    winners = []
    current_election = None
    current_post = None

    for row in rows:

        election_name = row[0]
        academic_year = row[1]
        post_name = row[2]
        student_name = row[3]
        register_no = row[4]
        total_votes = row[5]

        # New election OR new post
        if (
            election_name != current_election
            or post_name != current_post
        ):

            winners.append({
                "election_name": election_name,
                "academic_year": academic_year,
                "post_name": post_name,
                "student_name": student_name,
                "register_no": register_no,
                "total_votes": total_votes
            })

            current_election = election_name
            current_post = post_name

    cursor.close()

    return render_template(
        "winner.html",
        winners=winners
    )
# Student Login Page
@app.route("/student-login", methods=["GET", "POST"])
def student_login():

    if request.method == "POST":

        register_no = request.form["register_no"]
        password = request.form["password"]

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT *
            FROM students
            WHERE register_no=%s
            AND password=%s
        """, (register_no, password))

        student = cursor.fetchone()

        cursor.close()

        if student:

            session["student_id"] = student[0]
            session["register_no"] = student[1]
            session["student_name"] = student[2]

            flash("Login Successful", "success")

            return redirect(url_for("student_dashboard"))

        else:

            flash("Invalid Register Number or Password", "danger")

    return render_template("student_login.html")


# Student Dashboard
@app.route("/student-dashboard")
def student_dashboard():

    if "student_id" not in session:

        return redirect(url_for("student_login"))

    return render_template("student_dashboard.html")


# Student Logout
@app.route("/student-logout")
def student_logout():

    session.clear()

    flash("Logged out successfully", "success")

    return redirect(url_for("student_login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)