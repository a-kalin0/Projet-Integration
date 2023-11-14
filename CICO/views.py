from django.shortcuts import render, redirect
from django.views.generic import ListView

from CICO.forms import ConnectionForm, NewAccountForm, ForgottenPassword, NewPassword, ContactUsForm, CatSubmitForm, CodeForm
from django.contrib.auth import authenticate, login, get_user_model, logout

from .models import Statuses, UserCICO, Cats, DeviceRecords, Trigger

from django.shortcuts import redirect
from CICO.forms import ContactUsForm
from CICO.forms import ConnectionForm
from CICO.forms import NewAccountForm

from CICO.forms import AddDeviceNumber

import logging

logger = logging.getLogger('django')
from django.http import HttpResponse
from django.core.mail import EmailMessage, send_mail
from django.contrib.sites.shortcuts import get_current_site
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.template.loader import render_to_string
from .tokens import account_activation_token, password_reset_token
from django.db.models import F
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.forms.models import model_to_dict
from django.core.files.storage import default_storage
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from .serializers import CatSerializer
from django.core.exceptions import ValidationError
from random import randint
from datetime import datetime
from django.urls import reverse

LIST_SIZE = 2

def UpdateList(request, deviceId, date="00-00-000"):
    recordList = GetRecords(deviceId, date)[::-1]
    newList = recordList[request.session['listStart']:request.session['listStart'] + LIST_SIZE]
    if len(newList) == 0:
        newList = recordList[request.session['listStart'] - LIST_SIZE:request.session['listStart']]
        request.session['listStart'] -= LIST_SIZE

    return newList

def GetRecords(deviceId,date):
    if date == "00-00-0000":
        querySet = DeviceRecords.objects.filter(deviceId=deviceId).annotate(catName=F('trigger__catId__name'))
    else:
        dateObject = datetime.strptime(date, '%Y-%m-%d').date()
        querySet = DeviceRecords.objects.filter(deviceId=deviceId,
            time__year=dateObject.year, time__month=dateObject.month,
                                            time__day=dateObject.day).annotate(catName=F('trigger__catId__name'))
    return querySet.values()

def Empty(request):
    return redirect("CICO/")

# Create your views here.

def checkIP(request):
    print(request.session['IP'], request.META.get("REMOTE_ADDR"))
    if request.session['IP'] != request.META.get("REMOTE_ADDR"):
        return False
    else:
        return True


def vue(request):
    return render(request, 'CICO/index.html')

def generateCode():
    return str(randint(100000,999999)) #starts from 100000 to be sure that the number has at least 6 digits (and i'm too lazy to find a better way to do it)

def mail_sent(request):
    if request.method == "POST":
        form = CodeForm(request.POST)
        if form.is_valid():
            if form.cleaned_data["code"] == request.session["validationCode"]:
                request.session["validationCode"] = ""
                return redirect(newpassword)
            else:
                print("wrong code")
        else:
            print("form invalid")
    form = CodeForm()
    return render(request, 'CICO/mail_sent.html', {"form":form})


def reset_done(request):
     return render(request, "CICO/password_reset_complete.html")

def logoutPage(request):
    logout(request)
    request.session['IP'] = ""
    return redirect("connexion", formType="connexion")


def connection(request, formType):


    if (formType == "connexion"):
        if (request.method == "POST"):
            form = ConnectionForm(request.POST)
            if form.is_valid():
                user = authenticate(username=form.cleaned_data["identification"],
                                    password=form.cleaned_data["password"])
                if user is not None:
                    login(request, user)
                    request.session['IP'] = request.META.get("REMOTE_ADDR")
                    request.session['user'] = user.id
                    return redirect('profileIndex')
                else:
                    logger.info("login failed")
        else:
            form = ConnectionForm()
    elif (formType == "nouveauCompte"):
        if (request.method == "POST"):
            form = NewAccountForm(request.POST)
            if form.is_valid():
                if form.cleaned_data["email"] in UserCICO.objects.values_list("email", flat=True):
                    logger.info("This email is already used")  # these texts will need to be displayed on the page
                elif form.cleaned_data["password"] != form.cleaned_data["confirmPassword"]:
                    logger.info("Passwords not identical")
                else:
                    newUser = UserCICO.objects.create(email=form.cleaned_data["email"],
                                                      username=form.cleaned_data["identification"])
                    newUser.set_password(form.cleaned_data["password"])
                    newUser.is_active = False
                    newUser.save()
    
                    current_site = get_current_site(request)
                    mail_subject = "Confirmation d'inscription"
                    message = render_to_string('CICO/acc_activate_email.html', {
                                'user': newUser,
                                'domain': current_site.domain,
                                'uid':urlsafe_base64_encode(force_bytes(newUser.pk)),
                                'token':account_activation_token.make_token(newUser),
                            })
                    to_email = form.cleaned_data.get('email')
                    email = EmailMessage(
                                mail_subject, message, to=[to_email]
                    )
                    email.send()
                    return redirect('../mail_sent')

                    #request.session['user'] = newUser.id  # A backend authenticated the credentials
                    #return redirect('profileIndex')

        else:
            form = NewAccountForm()

    return render(request, 'CICO/connexion.html', {"form": form})




def profileIndex(request):
    if not checkIP(request) or not request.user.is_authenticated:
        return render(request, 'CICO/unauthorized.html', status=401)
    if (UserCICO.objects.get(username=request.user).ownedDevice == None):
        return redirect("profileNoDevice")
    try:
        request.session['listStart']
    except:
        request.session['listStart'] = 0

    try:
        request.session["filterDate"]
    except:
        request.session["filterDate"] = "00-00-0000"



    if request.method == "GET":
        recordList = UpdateList(request, UserCICO.objects.get(username=request.user).ownedDevice, request.session["filterDate"] )
        return render(request, 'CICO/profileIndex.html',
                      {"user": request.user.username, "recordList": recordList, "date":request.session["filterDate"]})

    elif request.method == "POST":
        try:
            datetime.strptime(request.POST["bouton"], '%Y-%m-%d').date()
        except:
            print("no date selected, using default value")
        else:
            request.session["filterDate"] = request.POST["bouton"]
            request.session['listStart'] = 0

        if request.POST["bouton"] == "Annuler":
            request.session["filterDate"] = "00-00-0000"
        elif request.POST["bouton"] == "récent":
            request.session['listStart'] = max(0, request.session[
            'listStart'] - LIST_SIZE)  # the max function is used to prevent the substraction from resulting in a negative
        elif request.POST["bouton"] == "ancien":
            request.session['listStart'] += LIST_SIZE

    
    return redirect("profileIndex")



def getProfileIndex(request, recordList):
    return render(request, 'CICO/profileIndex.html')

def profileNoDevice(request):
    message = ""
    if (request.method == "POST"):
        form = AddDeviceNumber(request.POST)
        if form.is_valid():
            number = form.cleaned_data["deviceNumber"]
            if number in UserCICO.objects.values_list("ownedDevice", flat=True):
                message = "Wrong device number"
                return render(request, 'CICO/profileNoDevice.html', {"form": form, "message": message})
            user = UserCICO.objects.get(username=request.user)
            user.ownedDevice = number
            user.save()
            return redirect('profileIndex', listButton="None")
    else:
        form = AddDeviceNumber()
        return render(request, 'CICO/profileNoDevice.html', {"form":form})


def faq(request):
    return render(request, 'CICO/faq.html')


def contact(request):
    return render(request, 'CICO/contact.html')


def commande(request):
    return render(request, 'CICO/commande.html')



def activate(request, uidb64, token):
    """Check the activation token sent via mail"""
    User = get_user_model()
    print(request.POST["uidb64"])
    print(request.POST["token"])
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except(TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.save()
        login(request, user)
        return redirect('/CICO')
    else:
        return HttpResponse('Activation link is invalid!')
    

def forgotpassword(request):
    if request.method == "POST":
        password_reset_form = ForgottenPassword(request.POST)
        if password_reset_form.is_valid():
            data = password_reset_form.cleaned_data['email']
            request.session["passwordResetEmail"] = data
            request.session["validationCode"] = generateCode()
            associated_users = UserCICO.objects.filter(email=data)
            if associated_users.exists():
                for user in associated_users:
                    subject = "Password Reset Requested"
                    email_template_name = "CICO/password_reset_email.html"
                    c = {
                        "email": user.email,
                        'site_name': 'YourWebsite',
                        "user": user,
                        "code": request.session["validationCode"],
                        'protocol': 'http',
                    }
                    email = render_to_string(email_template_name, c)
                    try:
                        send_mail(subject, email, 'server@example.com', [user.email], fail_silently=False)
                    except Exception as e:
                        return HttpResponse('Invalid header found.')
                return redirect('mail_sent')
    password_reset_form = ForgottenPassword()
    return render(request, "CICO/resetpassword.html", context={"password_reset_form": password_reset_form})


def newpassword(request):
    if request.method == 'POST':
        new_password_form = NewPassword(request.POST)
        if new_password_form.is_valid():
            new_password = new_password_form.cleaned_data['newPassword']
            user = UserCICO.objects.get(email=request.session["passwordResetEmail"])
            user.set_password(new_password)
            user.save()
            request.session["passwordResetEmail"] = ""
            logger.info(f"Password changed for user {user.username}")
            return redirect('reset_done')  # Rediriger vers la page de réussite
    else:
        new_password_form = NewPassword()

    return render(request, "CICO/newpassword.html", context={"form": new_password_form})


    """

    assert uidb64 is not None and token is not None

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = UserCICO.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, UserCICO.DoesNotExist):
        user = None

    if user is not None and password_reset_token.check_token(user, token):
        # Le jeton est valide, l'utilisateur peut réinitialiser son mot de passe
        if request.method == 'POST':
            new_password_form = NewPassword(request.POST)
            if new_password_form.is_valid():
                new_password = new_password_form.cleaned_data['newPassword']
                user.set_password(new_password)
                user.save()
                logger.info(f"Password changed for user {user.username}")
                return redirect('reset_done')  # Rediriger vers la page de réussite
        else:
            new_password_form = NewPassword()

        return render(request, "CICO/newpassword.html", context={"form": new_password_form})
    else:
        return HttpResponse('The reset link is invalid, possibly because it has already been used. Please request a new password reset.')
    """
@login_required
def add_cat(request):
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        form = CatSubmitForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                cat = form.save(commit=False)
                cat.ownerId = request.user  # Set ownerId to the current user
                cat.clean()  # Call full_clean to run all other validations including clean()
                cat.save()
                return JsonResponse({'success': True, 'catName' : cat.name}, status=201)  # Or any other success response
            
            except ValidationError:
                return JsonResponse({'success': False, 'errors': form.errors}, status=405)
        else:
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    return JsonResponse({'success': False, 'errors': 'Invalid request'}, status=400)
    
@login_required
def get_cats(request):
    if request.user.is_authenticated:
        user_cats = Cats.objects.filter(ownerId_id=request.user).values_list('name', flat=True)
        return JsonResponse(list(user_cats), safe=False)
    return JsonResponse({'error': 'User not authenticated'}, status=401)


def profile(request):
    if not checkIP(request) or not request.user.is_authenticated:
        return render(request, 'CICO/unauthorized.html', status=401)

    user = UserCICO.objects.get(username=request.user)

    if request.method == "POST":
        if list(request.POST.keys())[1] == "deleteAccount":
            user.delete()
            return redirect("connexion", formType="connexion")
        setattr(user,str(list(request.POST.keys())[1]), str(list(request.POST.values())[1]))
        user.save()
        return redirect("profile")
    else:
        return render(request, "CICO/profile.html", {"user":user})
