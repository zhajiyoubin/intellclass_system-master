import os
from flask import Flask, jsonify, render_template, request, flash, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from scheduler import SmartScheduler
from sqlalchemy import inspect

# 获取项目根目录路径（假设main.py在src目录下）
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
templates_path = os.path.join(base_dir, 'templates')
static_path = os.path.join(base_dir, 'static')

# 初始化Flask应用
app = Flask(__name__,
            template_folder=templates_path,
            static_folder=static_path)

# 数据库配置
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123456@localhost:3305/intellclass_system'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your-very-secret-key-here'

# 初始化数据库
db = SQLAlchemy(app)

# 用户模型
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'

# 初始化数据库表
def initialize_database():
    with app.app_context():
        # 检查表是否存在
        inspector = inspect(db.engine)
        if not inspector.has_table('user'):
            db.create_all()
            print("数据库表创建成功")
        else:
            print("数据库表已存在")

# 调用初始化函数
initialize_database()

# 自定义静态文件处理器
@app.route('/static/<path:filename>')
def custom_static(filename):
    # 添加调试信息
    file_path = os.path.join(app.static_folder, filename)
    print(f"请求静态文件: {filename}")
    print(f"完整路径: {file_path}")

    if not os.path.exists(file_path):
        print(f"文件不存在: {filename}")
        return "File not found", 404

    return send_from_directory(app.static_folder, filename)

# 路由定义
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            flash('登录成功!', 'success')
            return redirect(url_for('home'))
        else:
            flash('用户名或密码错误', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'danger')
        else:
            new_user = User(
                username=username,
                password=generate_password_hash(password, method='sha256')
            )
            db.session.add(new_user)
            db.session.commit()
            flash('注册成功!', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/api/create_schedule', methods=['POST'])
def create_schedule():
    data = request.json
    scheduler = SmartScheduler()
    schedule, errors = scheduler.generate_schedule(
        data['classes'],
        data['teachers'],
        data['classrooms']
    )
    return jsonify({
        "success": not bool(errors),
        "schedule": schedule,
        "errors": errors or None
    })

# 增强的调试信息路由
@app.route('/debug')
def debug_info():
    static_files = []
    try:
        static_files = os.listdir(app.static_folder)
    except Exception as e:
        static_files = [f"Error: {str(e)}"]

    template_files = []
    try:
        template_files = os.listdir(app.template_folder)
    except Exception as e:
        template_files = [f"Error: {str(e)}"]

    return f"""
    <h1>调试信息</h1>
    <h2>路径信息</h2>
    <p>项目根目录: {base_dir}</p>
    <p>静态文件路径: {app.static_folder}</p>
    <p>模板路径: {app.template_folder}</p>
    
    <h2>静态文件列表</h2>
    <ul>
        {"".join(f"<li>{f}</li>" for f in static_files)}
    </ul>
    
    <h2>模板文件列表</h2>
    <ul>
        {"".join(f"<li>{f}</li>" for f in template_files)}
    </ul>
    
    <h2>数据库信息</h2>
    <p>数据库URI: {app.config['SQLALCHEMY_DATABASE_URI']}</p>
    <p>用户表记录数: {User.query.count()}</p>
    """

if __name__ == '__main__':
    print("="*50)
    print(f"项目根目录: {base_dir}")
    print(f"静态文件路径: {app.static_folder}")
    print(f"模板路径: {app.template_folder}")

    # 打印静态文件列表
    try:
        print("静态文件列表:")
        for f in os.listdir(app.static_folder):
            print(f" - {f}")
    except Exception as e:
        print(f"无法读取静态文件夹: {str(e)}")

    # 打印模板文件列表
    try:
        print("模板文件列表:")
        for f in os.listdir(app.template_folder):
            print(f" - {f}")
    except Exception as e:
        print(f"无法读取模板文件夹: {str(e)}")

    print("="*50)

    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"启动失败: {str(e)}")
