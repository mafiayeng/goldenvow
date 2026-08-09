from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, FloatField, DateTimeField, TextAreaField, BooleanField, SelectField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, ValidationError, Regexp
from flask_wtf.file import FileField, FileAllowed

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(), 
        Length(min=3, max=100),
        Regexp(r'^[a-zA-Z0-9_]+$', message='Username can only contain letters, numbers, and underscores.')
    ])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[DataRequired(), Length(max=20)])
    super_secret = StringField('Super Admin Secret', validators=[Optional()])
    referral_code = StringField('Referral Code', validators=[Optional()])

class EventForm(FlaskForm):
    event_type = SelectField('Event Type', choices=[
        ('dowry', 'Dowry'), ('burial', 'Burial'), ('medical', 'Medical'),
        ('education', 'Education'), ('harambee', 'Harambee'), ('other', 'Other')
    ], validators=[DataRequired()])
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[Optional()])
    target_amount = FloatField('Target Amount (KES)', validators=[DataRequired(), NumberRange(min=1)])
    deadline = DateTimeField('Deadline', validators=[DataRequired()], format='%Y-%m-%dT%H:%M')
    event_date = DateTimeField('Event Date', validators=[DataRequired()], format='%Y-%m-%dT%H:%M')
    picture = FileField('Event Picture', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')])
    background_image = FileField('Background Image', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')])
    account_name = StringField('Account Name', validators=[Optional(), Length(max=150)])
    paybill = StringField('Paybill', validators=[Optional(), Length(max=50)])
    mpesa_number = StringField('M-Pesa Number', validators=[Optional(), Length(max=20)])
    till_number = StringField('Till Number', validators=[Optional(), Length(max=50)])
    bank_name = StringField('Bank Name', validators=[Optional(), Length(max=100)])
    bank_account_name = StringField('Bank Account Name', validators=[Optional(), Length(max=100)])
    bank_account_number = StringField('Bank Account Number', validators=[Optional(), Length(max=50)])
    payment_instructions = TextAreaField('Payment Instructions', validators=[Optional()])
    whatsapp_contact = StringField('WhatsApp Contact', validators=[Optional(), Length(max=20)])
    grace_period = FloatField('Grace Period (hours)', validators=[Optional(), NumberRange(min=0)])
    lock_message = TextAreaField('Lock Message (shown when page is locked)', validators=[Optional()])

class ContributorLoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')

class ContributorRegisterForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(), 
        Length(min=3, max=100),
        Regexp(r'^[a-zA-Z0-9_]+$', message='Username can only contain letters, numbers, and underscores.')
    ])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    name = StringField('Full Name', validators=[DataRequired(), Length(max=150)])
    phone = StringField('Phone', validators=[DataRequired(), Length(max=20)])

class ContactForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=150)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    subject = StringField('Subject', validators=[DataRequired(), Length(max=200)])
    message = TextAreaField('Message', validators=[DataRequired()])

class ProfileForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[DataRequired(), Length(max=20)])
    new_password = PasswordField('New Password (leave blank to keep current)', validators=[Optional(), Length(min=8)])

class SettingsForm(FlaskForm):
    maintenance_mode = BooleanField('Enable Maintenance Mode')
    maintenance_message = TextAreaField('Maintenance Message', validators=[Optional()])
    maintenance_eta = StringField('Estimated Return Time', validators=[Optional()])

class ForgotPasswordForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])

class ResetPasswordCodeForm(FlaskForm):
    code = StringField('Reset Code', validators=[DataRequired(), Length(min=6, max=6)])
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField('Confirm Password', validators=[DataRequired(), Length(min=8)])
    def validate_confirm(self, field):
        if field.data != self.password.data:
            raise ValidationError('Passwords must match.')

class ContributorForgotPasswordForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])

class ContributorResetPasswordCodeForm(FlaskForm):
    code = StringField('Reset Code', validators=[DataRequired(), Length(min=6, max=6)])
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField('Confirm Password', validators=[DataRequired(), Length(min=8)])
    def validate_confirm(self, field):
        if field.data != self.password.data:
            raise ValidationError('Passwords must match.')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField('Confirm Password', validators=[DataRequired(), Length(min=8)])
    def validate_confirm(self, field):
        if field.data != self.password.data:
            raise ValidationError('Passwords must match.')
