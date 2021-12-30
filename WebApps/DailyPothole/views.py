from django.shortcuts import render
from django.views.generic import TemplateView
from django.views import generic
from django.db.models import Q

from .models import *
from django.http import JsonResponse
import json
from django.core.exceptions import ObjectDoesNotExist


## Special case due to bad data design. Need to take care of CW_RESURFACING 1, 2 and 3 operation in special filter
def filter_out_excluded_operation_boro(query_set):
    query_set = query_set.exclude(
        ## Keep only Queens for CW 1
        ( Q(operation_id__operation__exact='CW_RESURFACING 1') & Q(boro_id__boro_long__exact='BRONX') )
        | ( Q(operation_id__operation__exact='CW_RESURFACING 1') & Q(boro_id__boro_long__exact='BROOKLYN') )
        | ( Q(operation_id__operation__exact='CW_RESURFACING 1') & Q(boro_id__boro_long__exact='MANHATTAN') )
        | ( Q(operation_id__operation__exact='CW_RESURFACING 1') & Q(boro_id__boro_long__exact='STATEN ISLAND') )

        ## Keep only Brooklyn for CW 2
        | ( Q(operation_id__operation__exact='CW_RESURFACING 2') & Q(boro_id__boro_long__exact='BRONX') )
        | ( Q(operation_id__operation__exact='CW_RESURFACING 2') & Q(boro_id__boro_long__exact='MANHATTAN') )
        | ( Q(operation_id__operation__exact='CW_RESURFACING 2') & Q(boro_id__boro_long__exact='QUEENS') )
        | ( Q(operation_id__operation__exact='CW_RESURFACING 2') & Q(boro_id__boro_long__exact='STATEN ISLAND') )

        ## Keep only Staten Island for CW 3
        | ( Q(operation_id__operation__exact='CW_RESURFACING 3') & Q(boro_id__boro_long__exact='BRONX') )
        | ( Q(operation_id__operation__exact='CW_RESURFACING 3') & Q(boro_id__boro_long__exact='BROOKLYN') )
        | ( Q(operation_id__operation__exact='CW_RESURFACING 3') & Q(boro_id__boro_long__exact='MANHATTAN') )
        | ( Q(operation_id__operation__exact='CW_RESURFACING 3') & Q(boro_id__boro_long__exact='QUEENS') )
    )

    return query_set


## Used by raw sql: Special case due to bad data design. Need to take care of CW_RESURFACING 1, 2 and 3 operation in special filter.
def get_excluded_operation_boro_as_where_cond():
    return """
        (
            tblOperation.[Operation] NOT IN ( 'CW_RESURFACING 1', 'CW_RESURFACING 2', 'CW_RESURFACING 3' )
            OR ( tblOperation.[Operation] = 'CW_RESURFACING 1' AND tblBoro.[BoroLong] = 'QUEENS' )
            OR ( tblOperation.[Operation] = 'CW_RESURFACING 2' AND tblBoro.[BoroLong] = 'BROOKLYN' )
            OR ( tblOperation.[Operation] = 'CW_RESURFACING 3' AND tblBoro.[BoroLong] = 'STATEN ISLAND' )
        )
    """


## Return a list of Operations that the client has access to. Returns not limited to 1 Operation, can be multiple.
def get_user_operation_and_boro_permission(username):
    try:
        permission_query = TblPermission.objects.using('DailyPothole').filter(
            user_id__username__exact=username
        ).order_by('operation_id')

        if permission_query.count() > 0:
            return {
                "success": True,
                "err": "",
                "operation_permission_list": [each.operation_id for each in permission_query],
                "operation_long_permission_list": [each.operation_id.operation for each in permission_query],
                "boro_permission_list": [each.boro_id for each in permission_query],
                "boro_long_permission_list": [each.boro_id.boro_long for each in permission_query],
                "permission_pair_op_boro_list": [(each.operation_id.operation, each.boro_id.boro_long) for each in permission_query],
            }
        return {
            "success": False,
            "err": "Cannot find any permissions for '{}'".format(username),
        }
    except Exception as e:
        print("Exception: DailyPothole: get_user_operation_and_boro_permission(): {}".format(e))
        return {
            "success": False,
            "err": 'Exception: DailyPothole: get_user_operation_and_boro_permission(): {}'.format(e),
        }


## Check if remote user is admin and is active
def user_is_active_admin(username):
    try:
        admin_query = TblUser.objects.using('DailyPothole').filter(
            username=username,
            is_admin=True, ## Filters for Admins
        )
        if admin_query.count() > 0:
            return {
                "isAdmin": True,
                "err": "",
            }
        return {
            "isAdmin": False,
            "err": '{} is not an active Admin'.format(username),
        }
    except Exception as e:
        print("Exception: user_is_active_admin(): {}".format(e))
        return {
            "isAdmin": None,
            "err": 'Exception: user_is_active_admin(): {}'.format(e),
        }


# Create your views here.
class HomePageView(TemplateView):
    template_name = 'DailyPothole.template.home.html'
    client_is_admin = False

    def get_context_data(self, **kwargs):
        try:
            ## Call the base implementation first to get a context
            context = super().get_context_data(**kwargs)
            self.client_is_admin = user_is_active_admin(self.request.user)["isAdmin"]
            context["client_is_admin"] = self.client_is_admin
            return context
        except Exception as e:
            context["client_is_admin"] = False
            return context


class AboutPageView(TemplateView):
    template_name = 'DailyPothole.template.about.html'


class ContactPageView(TemplateView):
    template_name = 'DailyPothole.template.contact.html'


class PotholeDataEntryPageView(generic.ListView):
    template_name = 'DailyPothole.template.datacollection.html'
    context_object_name = 'not_used'

    req_success = False
    err_msg = ""

    client_is_admin = False
    operation_list = []
    boro_list = []
    today = None

    def get_queryset(self):
        # Check for Active Admins
        self.client_is_admin = user_is_active_admin(self.request.user)["isAdmin"]

        ## Get the core data
        try:
            if self.client_is_admin:
                self.operation_list = [each.operation for each in TblOperation.objects.using('DailyPothole').all()]
                self.boro_list = [each.boro_long for each in TblBoro.objects.using('DailyPothole').all()]
            else:
                ## Get the remote user's Operation list and Borough list
                permission_obj = TblPermission.objects.using('DailyPothole').filter(
                    user_id__username__exact=self.request.user
                ).order_by('operation_id')

                if permission_obj.count() == 0:
                    raise ValueError("'{}' does not have any permission to view this page".format(self.request.user))


                self.operation_list = list(set([each.operation_id.operation for each in permission_obj]))
                self.boro_list = list(set([each.boro_id.boro_long for each in permission_obj]))

        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: DateCollectionPageView(): get_queryset(): {}".format(e)
            print(self.err_msg)
            return None

        self.req_success = True
        return None

    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)

            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = self.client_is_admin
            context["operation_list"] = self.operation_list
            context["boro_list"] = self.boro_list
            from django.utils import timezone as tz, dateformat
            context["today"] = dateformat.format(tz.localtime(tz.now()).date(), 'Y-m-d')
            return context
        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: DateCollectionPageView(): get_context_data(): {}".format(e)
            print(self.err_msg)

            context = super().get_context_data(**kwargs)
            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = False
            context["operation_list"] = []
            context["boro_list"] = []
            context["today"] = None
            return context


class PotholeDataGridPageView(generic.ListView):
    template_name = 'DailyPothole.template.datagrid.html'
    context_object_name = 'daily_pothole'

    req_success = False
    err_msg = ""

    client_is_admin = False

    def get_queryset(self):
        # Check for Active Admins
        self.client_is_admin = user_is_active_admin(self.request.user)["isAdmin"]

        ## Get the core data
        try:
            if self.client_is_admin:
                import datetime
                from dateutil.relativedelta import relativedelta
                now = datetime.datetime.now().strftime("%Y-%m-%d")
                then = (datetime.datetime.now() - relativedelta(weeks=2)).strftime("%Y-%m-%d")
                pothole_data = TblPotholeMaster.objects.using('DailyPothole').filter(
                    repair_date__range=[then, now]
                )
                pothole_data = filter_out_excluded_operation_boro(pothole_data)
                pothole_data.order_by('-repair_date', 'operation_id', 'boro_id')
            else:
                raise ValueError("'{}' is not an Admin, and is not authorized to see this page.".format(self.request.user))

        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: PotholeDataGridPageView(): get_queryset(): {}".format(e)
            print(self.err_msg)
            return None

        self.req_success = True
        return pothole_data

    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)

            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = self.client_is_admin
            return context
        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: PotholeDataGridPageView(): get_context_data(): {}".format(e)
            print(self.err_msg)

            context = super().get_context_data(**kwargs)
            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = False
            return context


class ComplaintsInputPageView(generic.ListView):
    template_name = 'DailyPothole.template.complaintsinput.html'
    context_object_name = 'complaints'

    req_success = False
    err_msg = ""

    client_is_admin = False

    def get_queryset(self):
        # Check for Active Admins
        self.client_is_admin = user_is_active_admin(self.request.user)["isAdmin"]

        ## Get the core data
        try:
            if self.client_is_admin:
                import datetime
                from dateutil.relativedelta import relativedelta
                now = datetime.datetime.now().strftime("%Y-%m-%d")
                then = (datetime.datetime.now() - relativedelta(weeks=2)).strftime("%Y-%m-%d")
                complaints_data = TblComplaint.objects.using('DailyPothole').filter(
                    complaint_date__range=[then, now]
                ).order_by('complaint_date')
            else:
                raise ValueError("'{}' is not an Admin, and is not authorized to see this page.".format(self.request.user))

        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: ComplaintsInputPageView(): get_queryset(): {}".format(e)
            print(self.err_msg)
            return TblComplaint.objects.none()

        self.req_success = True
        return complaints_data

    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)

            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = self.client_is_admin
            return context
        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: ComplaintsInputPageView(): get_context_data(): {}".format(e)
            print(self.err_msg)

            context = super().get_context_data(**kwargs)
            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = False
            return context


class ReportsPageView(generic.ListView):
    template_name = 'DailyPothole.template.reports.html'
    context_object_name = 'complaints'

    req_success = False
    err_msg = ""

    client_is_admin = False

    def get_queryset(self):
        # Check for Active Admins
        self.client_is_admin = user_is_active_admin(self.request.user)["isAdmin"]

        ## Get the core data
        try:
            if self.client_is_admin:
                complaints_data = TblComplaint.objects.none()
            else:
                raise ValueError("'{}' is not an Admin, and is not authorized to see this page.".format(self.request.user))

        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: ReportsPageView(): get_queryset(): {}".format(e)
            print(self.err_msg)
            return TblComplaint.objects.none()

        self.req_success = True
        return complaints_data

    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)

            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = self.client_is_admin
            return context
        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: ReportsPageView(): get_context_data(): {}".format(e)
            print(self.err_msg)

            context = super().get_context_data(**kwargs)
            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = False
            return context


## Create User Mgmt view
def UpdatePotholesData(request):

    if request.method != "POST":
        return JsonResponse({
            "post_success": True,
            "post_msg": "{} HTTP request not supported".format(request.method),
        })


    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: UpdatePotholesData(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "UpdatePotholesData():\n\nUNAUTHENTICATE USER!",
            "post_data": None,
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: UpdatePotholesData():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    try:
        type_of_pothole_info            = json_blob['type_of_pothole_info']
        date_of_repair_input            = json_blob['date_of_repair_input']
        operation_input                 = json_blob['select_operation_input']
        borough_input                   = json_blob['select_borough_input']
        pothole_crew_count_input        = json_blob['pothole_crew_count_input']
        regular_holes_repaired_input    = json_blob['regular_holes_repaired_input']
        today_pothole_crew_count_input  = json_blob['today_pothole_crew_count_input']
        today_date_input                = json_blob['today_date_input']

        date_input = None
        if type_of_pothole_info not in ['PotholeData', 'TodayCrewData']:
            raise ValueError("Unrecognized input for type_of_pothole_info: '{}'".format(type_of_pothole_info))

        if type_of_pothole_info == 'PotholeData':
            if date_of_repair_input is None:
                raise ValueError("date_of_repair_input cannot be None")

            if operation_input is None:
                raise ValueError("operation_input cannot be None")

            if borough_input is None:
                raise ValueError("borough_input cannot be None")

            date_input = date_of_repair_input

        if type_of_pothole_info == 'TodayCrewData':
            if today_date_input is None:
                raise ValueError("today_date_input cannot be None")

            date_input = today_date_input

        try:
            if pothole_crew_count_input is not None:
                pothole_crew_count_input        = float(pothole_crew_count_input)
        except ValueError as e:
            raise ValueError("pothole_crew_count_input '{}' cannot be converted into an Decimal".format(pothole_crew_count_input))
        except Exception as e:
            raise

        try:
            if regular_holes_repaired_input is not None:
                regular_holes_repaired_input        = int(regular_holes_repaired_input)
        except ValueError as e:
            raise ValueError("regular_holes_repaired_input '{}' cannot be converted into an Int".format(regular_holes_repaired_input))
        except Exception as e:
            raise

        try:
            if today_pothole_crew_count_input is not None:
                today_pothole_crew_count_input        = float(today_pothole_crew_count_input)
        except ValueError as e:
            raise ValueError("today_pothole_crew_count_input '{}' cannot be converted into an Decimal".format(today_pothole_crew_count_input))
        except Exception as e:
            raise


        is_admin = user_is_active_admin(remote_user)["isAdmin"]
        if not is_admin:
            user_permissions = get_user_operation_and_boro_permission(remote_user)
            if user_permissions['success'] == False:
                raise ValueError('get_user_operation_and_boro_permission() failed: {}'.format(user_permissions['err']))
            else:
                allowed_permission_op_boro_pair = user_permissions['permission_pair_op_boro_list']

            if (operation_input, borough_input) not in allowed_permission_op_boro_pair:
                raise ValueError("'{}' does not have the permission to edit records related to '{}' and '{}'".format(remote_user, operation_input, borough_input))


        pothole_data = TblPotholeMaster.objects.using('DailyPothole')
        pothole_data = filter_out_excluded_operation_boro(pothole_data)
        pothole_data = pothole_data.get(
            operation_id__operation__exact=operation_input,
            boro_id__boro_long__exact=borough_input,
            repair_date__exact=date_input,
        )


        user_obj = TblUser.objects.using("DailyPothole").get(
            username__exact=remote_user,
        )

        from django.utils import timezone as tz, dateformat
        timestamp = tz.localtime(tz.now())

        if type_of_pothole_info == 'PotholeData':
            pothole_data.repair_crew_count = pothole_crew_count_input
            pothole_data.holes_repaired = regular_holes_repaired_input
            pothole_data.last_modified_stamp = timestamp
            pothole_data.last_modified_by_user_id = user_obj
            pothole_data.save()

        if type_of_pothole_info == 'TodayCrewData':
            pothole_data.daily_crew_count = today_pothole_crew_count_input
            pothole_data.last_modified_stamp = timestamp
            pothole_data.last_modified_by_user_id = user_obj
            pothole_data.save()

        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            # "type_of_pothole_info": type_of_pothole_info,
            # "date_of_repair_input": date_of_repair_input,
            # "operation_input": operation_input,
            # "borough_input": borough_input,
            # "pothole_crew_count_input": pothole_crew_count_input,
            # "regular_holes_repaired_input": regular_holes_repaired_input,
            # "today_pothole_crew_count_input": today_pothole_crew_count_input,
            # "today_date_input": today_date_input,
            # "timestamp": timestamp,
            # "user_id": user_obj.user_id,
            # "record": [pothole_data.pothole_master_id, pothole_data.repair_date, pothole_data.operation_id.operation_id, pothole_data.boro_id.boro_id, pothole_data.repair_crew_count, pothole_data.holes_repaired, pothole_data.daily_crew_count, pothole_data.last_modified_stamp, pothole_data.last_modified_by_user_id.user_id],
        })
    except ObjectDoesNotExist as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: UpdatePotholesData():\n\nError: {}. For '{}', '{}' and '{}'".format(e, date_input, operation_input, borough_input),
        })
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: UpdatePotholesData():\n\nError: {}".format(e),
            # "post_msg": "DailyPothole: UpdatePotholesData():\n\nError: {}. The exception type is:{}".format(e,  e.__class__.__name__),
        })


def UpdateComplaintsData(request):

    if request.method != "POST":
        return JsonResponse({
            "post_success": True,
            "post_msg": "{} HTTP request not supported".format(request.method),
        })


    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: UpdateComplaintsData(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "UpdateComplaintsData():\n\nUNAUTHENTICATE USER!",
            "post_data": None,
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: UpdateComplaintsData():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    try:
        complaint_date      = json_blob['complaint_date']
        fits_bronx          = json_blob['fits_bronx']
        fits_brooklyn       = json_blob['fits_brooklyn']
        fits_manhattan      = json_blob['fits_manhattan']
        fits_queens         = json_blob['fits_queens']
        fits_staten_island  = json_blob['fits_staten_island']
        open_siebel         = json_blob['open_siebel']


        from datetime import datetime
        datetime_obj = datetime.strptime(complaint_date, '%Y-%m-%d')

        if datetime_obj.date() > datetime.today().date():
            raise ValueError("Cannot enter data for dates in the future! (Date - '{}')".format(complaint_date))


        try:
            if fits_bronx is not None and fits_bronx != "":
                fits_bronx = int(fits_bronx)
            elif fits_bronx == "":
                fits_bronx = None
        except ValueError as e:
            raise ValueError("fits_bronx '{}' cannot be converted into an Int".format(fits_bronx))
        except Exception as e:
            raise

        try:
            if fits_brooklyn is not None and fits_brooklyn != "":
                fits_brooklyn = int(fits_brooklyn)
            elif fits_brooklyn == "":
                fits_brooklyn = None
        except ValueError as e:
            raise ValueError("fits_brooklyn '{}' cannot be converted into an Int".format(fits_brooklyn))
        except Exception as e:
            raise

        try:
            if fits_manhattan is not None and fits_manhattan != "":
                fits_manhattan = int(fits_manhattan)
            elif fits_manhattan == "":
                fits_manhattan = None
        except ValueError as e:
            raise ValueError("fits_manhattan '{}' cannot be converted into an Int".format(fits_manhattan))
        except Exception as e:
            raise

        try:
            if fits_queens is not None and fits_queens != "":
                fits_queens = int(fits_queens)
            elif fits_queens == "":
                fits_queens = None
        except ValueError as e:
            raise ValueError("fits_queens '{}' cannot be converted into an Int".format(fits_queens))
        except Exception as e:
            raise

        try:
            if fits_staten_island is not None and fits_staten_island != "":
                fits_staten_island = int(fits_staten_island)
            elif fits_staten_island == "":
                fits_staten_island = None
        except ValueError as e:
            raise ValueError("fits_staten_island '{}' cannot be converted into an Int".format(fits_staten_island))
        except Exception as e:
            raise

        try:
            if open_siebel is not None and open_siebel != "":
                open_siebel = int(open_siebel)
            elif open_siebel == "":
                open_siebel = None
        except ValueError as e:
            raise ValueError("open_siebel '{}' cannot be converted into an Int".format(open_siebel))
        except Exception as e:
            raise


        is_admin = user_is_active_admin(remote_user)["isAdmin"]
        if not is_admin:
            raise ValueError("'{}' is not admin and does not have the permission to edit complaints data".format(remote_user))


        complaint_data = TblComplaint.objects.using('DailyPothole').get(
            complaint_date__exact=complaint_date,
        )

        complaint_data.fits_bronx         = fits_bronx
        complaint_data.fits_brooklyn      = fits_brooklyn
        complaint_data.fits_manhattan     = fits_manhattan
        complaint_data.fits_queens        = fits_queens
        complaint_data.fits_staten_island = fits_staten_island
        complaint_data.siebel_complaints  = open_siebel
        complaint_data.save()


        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "complaint_date": complaint_date,
            "fits_bronx": fits_bronx,
            "fits_brooklyn": fits_brooklyn,
            "fits_manhattan": fits_manhattan,
            "fits_queens": fits_queens,
            "fits_staten_island": fits_staten_island,
            "open_siebel": open_siebel,
        })
    except ObjectDoesNotExist as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: UpdateComplaintsData():\n\nError: {}. For '{}'".format(e, complaint_date),
        })
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: UpdateComplaintsData():\n\nError: {}".format(e),
            # "post_msg": "DailyPothole: UpdateComplaintsData():\n\nError: {}. The exception type is:{}".format(e,  e.__class__.__name__),
        })


def LookupComplaintsData(request):

    if request.method != "POST":
        return JsonResponse({
            "post_success": True,
            "post_msg": "{} HTTP request not supported".format(request.method),
        })


    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: LookupComplaintsData(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "LookupComplaintsData():\n\nUNAUTHENTICATE USER!",
            "post_data": None,
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: LookupComplaintsData():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    try:
        complaint_date      = json_blob['complaint_date']

        is_admin = user_is_active_admin(remote_user)["isAdmin"]
        if not is_admin:
            raise ValueError("'{}' is not admin. Only admins can access the LookupComplaintsData() api".format(remote_user))


        complaint_data = TblComplaint.objects.using('DailyPothole').get(
            complaint_date__exact=complaint_date,
        )

        fits_bronx          = complaint_data.fits_bronx
        fits_brooklyn       = complaint_data.fits_brooklyn
        fits_manhattan      = complaint_data.fits_manhattan
        fits_queens         = complaint_data.fits_queens
        fits_staten_island  = complaint_data.fits_staten_island
        open_siebel         = complaint_data.siebel_complaints


        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "complaint_date": complaint_date,
            "fits_bronx": fits_bronx,
            "fits_brooklyn": fits_brooklyn,
            "fits_manhattan": fits_manhattan,
            "fits_queens": fits_queens,
            "fits_staten_island": fits_staten_island,
            "open_siebel": open_siebel,
        })
    except ObjectDoesNotExist as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: LookupComplaintsData():\n\nError: {}. For '{}'".format(e, complaint_date),
        })
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: LookupComplaintsData():\n\nError: {}".format(e),
            # "post_msg": "DailyPothole: LookupComplaintsData():\n\nError: {}. The exception type is:{}".format(e,  e.__class__.__name__),
        })


def GetPDFReport(request):
    if request.method != "POST":
        return JsonResponse({
            "post_success": True,
            "post_msg": "{} HTTP request not supported".format(request.method),
        })


    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: GetPDFReport(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "GetPDFReport():\n\nUNAUTHENTICATE USER!",
            "post_data": None,
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: GetPDFReport():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    try:
        report_date      = json_blob['report_date']

        is_admin = user_is_active_admin(remote_user)["isAdmin"]
        if not is_admin:
            raise ValueError("'{}' is not admin. Only admins can access the GetPDFReport() api".format(remote_user))

        from django.db.models import Sum, Count
        from datetime import datetime, timedelta
        daydelta            = 6
        report_date_obj     = datetime.strptime(report_date, '%Y-%m-%d')

        start               = report_date_obj - timedelta(days=report_date_obj.weekday()+2) # Get last week's weekends and current week's weekdays
        end                 = start + timedelta(days=daydelta)
        complaint_date_obj  = report_date_obj + timedelta(days=-1) # We want previous day's complaint data

        start_str           = start.strftime("%Y-%m-%d")
        end_str             = end.strftime("%Y-%m-%d")
        complaint_date      = complaint_date_obj.strftime("%Y-%m-%d")


        potholes_data = TblPotholeMaster.objects.using('DailyPothole').filter(
            repair_date__range=[start_str, end_str],
        ).order_by('operation_id', 'boro_id', 'repair_date')
        potholes_data = filter_out_excluded_operation_boro(potholes_data)

        complaint_data = TblComplaint.objects.using('DailyPothole').get(
            complaint_date__exact=complaint_date, # Get previous day's data
        )

        today_crew_count = TblPotholeMaster.objects.using('DailyPothole').filter(
            repair_date__exact=report_date,
        ).order_by('boro_id__boro_long', 'operation_id__operation')
        today_crew_count = filter_out_excluded_operation_boro(today_crew_count)

        # Assuming a new FY starts at July 1st
        fytd_start_str = "{}-07-01".format(report_date_obj.year - 1 if report_date_obj.month < 7 else report_date_obj.year)
        fytd_total_pothole_repair = TblPotholeMaster.objects.using('DailyPothole').filter(
            repair_date__range=[fytd_start_str, report_date],
        )
        fytd_total_pothole_repair = filter_out_excluded_operation_boro(fytd_total_pothole_repair)
        fytd_total_pothole_repair = fytd_total_pothole_repair.aggregate(total_repaired=Sum('holes_repaired'))

        weekly_by_boro = TblPotholeMaster.objects.using('DailyPothole').filter(
            repair_date__range=[start_str, end_str],
        ).values(
            'operation_id__operation'
            ,'boro_id__boro_long'
        ).annotate( ## When combining .values() and .annotate(), it is effectively an aggregation (From .annotate()) with a group by of the columns specified in .values()
            total_repaired=Sum('holes_repaired')
        ).order_by('operation_id__operation', 'boro_id__boro_long')

        unique_boro = TblPotholeMaster.objects.using('DailyPothole')
        unique_boro = filter_out_excluded_operation_boro(unique_boro)
        unique_boro = unique_boro.values('boro_id__boro_long').order_by('boro_id__boro_long').distinct()

        fiscal_year_by_boro = TblPotholeMaster.objects.using('DailyPothole').filter(
            repair_date__range=[fytd_start_str, report_date],
        ).values(
            'operation_id__operation'
            ,'boro_id__boro_long'
        ).annotate(
            total_repaired=Sum('holes_repaired')
        ).order_by('operation_id__operation', 'boro_id__boro_long')

        import io
        buffer = io.BytesIO()


        from reportlab.lib import colors, pagesizes
        from reportlab.platypus import SimpleDocTemplate, PageBreak
        from reportlab.platypus.tables import Table, TableStyle
        cm = 2.54

        whole_doc_elements = []
        doc = SimpleDocTemplate(
            buffer,
            # pagesize=pagesizes.landscape(pagesizes.letter),
            # pagesize=pagesizes.landscape(pagesizes.A1),
            pagesize=pagesizes.landscape(pagesizes.A2),
            # pagesize=pagesizes.A1,
            rightMargin=0,
            leftMargin=6.5 * cm,
            topMargin=0.3 * cm,
            bottomMargin=0,
        )

        ## Page 1
        ## General Grid
        header = ('Daily Pothole Report', '', '', report_date_obj.strftime("%A, %B %#d, %Y"))
        dates_header = ('', '', 'Saturday', '', 'Sunday', '', 'Monday', '', 'Tuesday', '', 'Wednesday', '', 'Thursday', '', 'Friday', '', 'Weekly Total', '')
        column_header = ('Borough\nOperation', '', 'Crews\nFielded', 'Holes\nRepaired', 'Crews\nFielded', 'Holes\nRepaired', 'Crews\nFielded', 'Holes\nRepaired', 'Crews\nFielded', 'Holes\nRepaired', 'Crews\nFielded', 'Holes\nRepaired', 'Crews\nFielded', 'Holes\nRepaired', 'Crews\nFielded', 'Holes\nRepaired', 'Crews\nFielded', 'Holes\nRepaired')

        format_data = [
            header,
            '', # Extra empty row
            dates_header,
            column_header,
        ]

        # data = [
        #     ('', 1          , 2         ),
        #     ('', 3          , 4         ),
        # ]
        data = []
        day_i = 0
        out_row = []
        crews_total = 0
        holes_total = 0
        for each in potholes_data:
            # On first day of the tracking week, append boro operation info
            if day_i == 0:
                out_row.append("{}\n{}".format(each.boro_id.boro_long, each.operation_id.operation))
                out_row.append(None)

            crew_count_cal      = float(each.repair_crew_count)    if each.repair_crew_count is not None   else None
            holes_repaired_cal  = int(each.holes_repaired )      if each.holes_repaired is not None      else None

            if crew_count_cal is not None and crew_count_cal.is_integer(): ## If crew count is a whole number, cast it as int
                crew_count_cal = int(crew_count_cal)

            crews_total += crew_count_cal if crew_count_cal is not None else 0
            holes_total += holes_repaired_cal if holes_repaired_cal is not None else 0

            out_row.append(crew_count_cal if crew_count_cal is not None else None)
            out_row.append(holes_repaired_cal if holes_repaired_cal is not None else None)

            # One week (7 days) worth of data has been processed, save it, and reset variables
            if day_i == daydelta:
                out_row.append(crews_total)
                out_row.append(holes_total)
                out_row_tuple = (out_row)
                data.append(out_row_tuple)

                day_i = 0
                out_row = []
                crews_total = 0
                holes_total = 0
            else:
                day_i += 1

        # Calculate Totals row (Last row of the table)
        sat_total_crews = 0
        sat_total_holes = 0
        sun_total_crews = 0
        sun_total_holes = 0
        mon_total_crews = 0
        mon_total_holes = 0
        tue_total_crews = 0
        tue_total_holes = 0
        wed_total_crews = 0
        wed_total_holes = 0
        thu_total_crews = 0
        thu_total_holes = 0
        fri_total_crews = 0
        fri_total_holes = 0
        week_total_crews = 0
        week_total_holes = 0
        for each in data:
            sat_total_crews += each[2]   if isinstance(each[2], int)  or isinstance(each[2], float)  else 0
            sat_total_holes += each[3]   if isinstance(each[3], int)  or isinstance(each[3], float)  else 0
            sun_total_crews += each[4]   if isinstance(each[4], int)  or isinstance(each[4], float)  else 0
            sun_total_holes += each[5]   if isinstance(each[5], int)  or isinstance(each[5], float)  else 0
            mon_total_crews += each[6]   if isinstance(each[6], int)  or isinstance(each[6], float)  else 0
            mon_total_holes += each[7]   if isinstance(each[7], int)  or isinstance(each[7], float)  else 0
            tue_total_crews += each[8]   if isinstance(each[8], int)  or isinstance(each[8], float)  else 0
            tue_total_holes += each[9]   if isinstance(each[9], int)  or isinstance(each[9], float)  else 0
            wed_total_crews += each[10]  if isinstance(each[10], int) or isinstance(each[10], float) else 0
            wed_total_holes += each[11]  if isinstance(each[11], int) or isinstance(each[11], float) else 0
            thu_total_crews += each[12]  if isinstance(each[12], int) or isinstance(each[12], float) else 0
            thu_total_holes += each[13]  if isinstance(each[13], int) or isinstance(each[13], float) else 0
            fri_total_crews += each[14]  if isinstance(each[14], int) or isinstance(each[14], float) else 0
            fri_total_holes += each[15]  if isinstance(each[15], int) or isinstance(each[15], float) else 0
            week_total_crews += each[16] if isinstance(each[16], int) or isinstance(each[16], float) else 0
            week_total_holes += each[17] if isinstance(each[17], int) or isinstance(each[17], float) else 0

        totals_tuple_row = (
            'Total'
            ,''
            ,sat_total_crews
            ,sat_total_holes
            ,sun_total_crews
            ,sun_total_holes
            ,mon_total_crews
            ,mon_total_holes
            ,tue_total_crews
            ,tue_total_holes
            ,wed_total_crews
            ,wed_total_holes
            ,thu_total_crews
            ,thu_total_holes
            ,fri_total_crews
            ,fri_total_holes
            ,week_total_crews
            ,week_total_holes
        )
        data.append(totals_tuple_row)

        for each_row in data:
            ## For last two element in each_row (Which is week_total_crews and week_total_holes), we assume it to be null (by assigning it True to the null check) because we are nulling checking the content of the each cell, and not the totals.
            ## We also assume first two element is null, because it's boro/operation info and an empty cell placeholder
            null_list = [each_cell is None if i > 1 and len(each_row) - i > 2 else True for i, each_cell in enumerate(each_row)]
            ## If entire row is null (not checking week_total_crews and week_total_holes, and assumed those two is null), don't add it to the final table
            if all(null_check == True for null_check in null_list):
                pass
            else:
                format_data.append(each_row)


        table = Table(
            format_data,
            colWidths=70,
        )
        ## The coordinates are given as (column, row) which follows the spreadsheet'A1' model,
        ## but not the more natural (for mathematicians) 'RC' ordering.
        ## The top left cell is (0, 0) the bottomright is (-1, -1).
        table.setStyle(TableStyle([
            ('BOX', (0,4), (-1,-1), 0.25, colors.black),

            ('LINEABOVE',   (2,4),      (-1,-1),    0.25,   colors.black),
            ('INNERGRID',   (2,4),      (-1,-1),    0.25,   colors.black),
            ('LINEABOVE',   (0,4),      (1,-1),     0.25,   colors.black),
            ('BOX',         (0,4),      (1,-1),     0.25,   colors.black),
            ('LINEAFTER',   (3,3),      (3,-1),     2.00,   colors.black),
            ('LINEAFTER',   (5,3),      (5,-1),     2.00,   colors.black),
            ('LINEAFTER',   (7,3),      (7,-1),     2.00,   colors.black),
            ('LINEAFTER',   (9,3),      (9,-1),     2.00,   colors.black),
            ('LINEAFTER',   (11,3),     (11,-1),    2.00,   colors.black),
            ('LINEAFTER',   (13,3),     (13,-1),    2.00,   colors.black),
            ('LINEAFTER',   (15,3),     (15,-1),    2.00,   colors.black),
            ('LINEABOVE',   (0,-1),     (-1,-1),    2.00,   colors.black),

            # For top header
            ('SPAN', (0,0), (1,0)),
            ('BACKGROUND', (0,0), (-1,1), colors.lightblue),
            ('FONTNAME', (0,0), (-1,1), 'Courier-Bold'),
            ('FONTSIZE', (3,0), (-1,0), 10),
            ('FONTSIZE', (0,0), (1,1), 17),


            # For week days header
            ('SPAN', (2,2), (3,2)),
            ('SPAN', (4,2), (5,2)),
            ('SPAN', (6,2), (7,2)),
            ('SPAN', (8,2), (9,2)),
            ('SPAN', (10,2), (11,2)),
            ('SPAN', (12,2), (13,2)),
            ('SPAN', (14,2), (15,2)),
            ('ALIGN',(2,2),(-1,2),'CENTER'),

        ]))
        whole_doc_elements.append(table)


        ## FITS grid
        data = [('Open FITS Complaints', 'Open Siebel Complaints')]

        if (
            complaint_data.fits_bronx is None
            and complaint_data.fits_brooklyn is None
            and complaint_data.fits_manhattan is None
            and complaint_data.fits_queens is None
            and complaint_data.fits_staten_island is None
            ):
            fits_total = 'No Data'
        else:
            fits_bronx = complaint_data.fits_bronx if complaint_data.fits_bronx is not None else 0
            fits_brooklyn = complaint_data.fits_brooklyn if complaint_data.fits_brooklyn is not None else 0
            fits_manhattan = complaint_data.fits_manhattan if complaint_data.fits_manhattan is not None else 0
            fits_queens = complaint_data.fits_queens if complaint_data.fits_queens is not None else 0
            fits_staten_island = complaint_data.fits_staten_island if complaint_data.fits_staten_island is not None else 0

            fits_total = fits_bronx + fits_brooklyn + fits_manhattan + fits_queens + fits_staten_island

        complaints_tuple = (
            fits_total
            ,complaint_data.siebel_complaints if complaint_data.siebel_complaints is not None else 'No Data'
        )
        data.append(complaints_tuple)
        table_fits_complaints = Table(
            data,
            colWidths=150,
        )
        table_fits_complaints.setStyle(TableStyle([
            ('BOX', (0,1), (-1,-1), 0.25, colors.black),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),

            # ('LINEABOVE', (0,1), (-1,-1), 0.25, colors.black),
            ('INNERGRID', (0,1), (-1,-1), 0.25, colors.black),

            ('FONTNAME', (0,0), (-1,0), 'Courier-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 11),
        ]))


        ## Today Crew Count Grid
        data = [
            ("Today's Crew Count ({})".format(report_date), "", ""),
            ('',) # Empty row
        ]
        total_crew_count = 0
        for each in today_crew_count:
            dly_crew_ct = each.daily_crew_count if each.daily_crew_count is not None else None
            dly_crew_ct = float(dly_crew_ct) if dly_crew_ct is not None else None
            if dly_crew_ct is not None and dly_crew_ct.is_integer(): ## If crew count is a whole number, cast it as int
                dly_crew_ct = int(dly_crew_ct)
            row_tuple = (
                "{}".format(each.boro_id.boro_long)
                ,"{}".format(each.operation_id.operation)
                ,dly_crew_ct
            )
            ## Only add row to the table if the daily_crew_count is not null
            if dly_crew_ct is not None:
                data.append(row_tuple)
            total_crew_count += dly_crew_ct if dly_crew_ct is not None else 0

        data.append(('Total', '', total_crew_count))

        table_daily_crew_count = Table(
            data,
            colWidths=150,
        )
        table_daily_crew_count.setStyle(TableStyle([
            ('BOX', (0,2), (-1,-1), 0.25, colors.black),

            ('LINEABOVE', (0,2), (-1,-2), 0.25, colors.black),
            ('LINEBELOW', (0,2), (-1,-2), 0.25, colors.black),
            ('INNERGRID', (0,2), (-1,-2), 0.25, colors.black),
            ('LINEABOVE', (0,-1),(-1,-1), 2.00, colors.black),

            ('FONTNAME', (0,0), (-1,0), 'Courier-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('FONTSIZE', (0,0), (0,0), 17),

        ]))


        ## Total FYTD Pothole Repaired Count Grid
        data = [
            ("Total Pothole Repairs - FYTD",),
            ('',) # Empty row
        ]
        data.append((fytd_total_pothole_repair['total_repaired'],))

        table_fytd_pothole_repaired = Table(
            data,
            colWidths=150,
        )
        table_fytd_pothole_repaired.setStyle(TableStyle([
            ('BOX', (0,2), (-1,-1), 0.25, colors.black),

            ('FONTNAME', (0,0), (-1,0), 'Courier-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('FONTSIZE', (0,0), (0,0), 17),

        ]))


        midsection_data = [[table_fits_complaints, table_daily_crew_count, table_fytd_pothole_repaired]]
        midsection_table = Table(
            midsection_data,
            colWidths=[350, 500, 200], # Set to 50 above what each table's total width is
        )
        midsection_table.setStyle(TableStyle([
            ('VALIGN',(0,0),(-1,-1),'TOP'),

        ]))
        whole_doc_elements.append(midsection_table)
        whole_doc_elements.append(PageBreak())


        ## Page 2
        header = ('Weekly Pothole Repairs by Borough', '', '', report_date_obj.strftime("%A, %B %#d, %Y"))
        dates_header_1 = ('From', start_str)
        dates_header_2 = ('To', end_str)
        # Should results in this: column_header = ('Operation', 'Bronx', 'Brooklyn', 'Manhattan', 'Queens', 'Staten Island', 'Operation Total')
        column_header = ['Operation']
        for each in unique_boro:
            column_header.append(each['boro_id__boro_long'])
        column_header.append('Operation Total')
        column_header = (column_header) # Convert to tuple, for immutability

        data = [
            header,
            '', # Empty row
            dates_header_1,
            dates_header_2,
            column_header,
        ]

        body_data = []
        boro_i = 0
        boro_count = unique_boro.count()
        out_row = []
        holes_total = 0
        for each in weekly_by_boro:
            # On first day of the tracking week, append boro operation info
            if boro_i == 0:
                out_row.append("{}".format(each['operation_id__operation']))

            holes_total += each['total_repaired'] if each['total_repaired'] is not None else 0
            out_row.append(each['total_repaired'] if each['total_repaired'] is not None else '')

            # 5 unique boro worth of data has been processed, save it, and reset variables
            if boro_i == boro_count-1:
                out_row.append(holes_total)
                out_row_tuple = (out_row)
                body_data.append(out_row_tuple)

                boro_i = 0
                out_row = []
                holes_total = 0
            else:
                boro_i += 1

        # Calculate Totals row (Last row of the table)
        bronx_total             = 0
        brooklyn_total          = 0
        manhattan_total         = 0
        queens_total            = 0
        staten_island_total     = 0
        operation_total_total   = 0
        for each in body_data:
            bronx_total             += each[1] if isinstance(each[1], int) else 0
            brooklyn_total          += each[2] if isinstance(each[2], int) else 0
            manhattan_total         += each[3] if isinstance(each[3], int) else 0
            queens_total            += each[4] if isinstance(each[4], int) else 0
            staten_island_total     += each[5] if isinstance(each[5], int) else 0
            operation_total_total   += each[6] if isinstance(each[6], int) else 0

        totals_tuple_row = (
            'Total'
            ,bronx_total
            ,brooklyn_total
            ,manhattan_total
            ,queens_total
            ,staten_island_total
            ,operation_total_total
        )
        body_data.append(totals_tuple_row)

        data = data + body_data # Concate the two list

        table_weekly_by_boro = Table(
            data,
            colWidths=150
        )
        table_weekly_by_boro.setStyle(TableStyle([
            ('BOX', (0,5), (-1,-1), 0.25, colors.black),
            ('INNERGRID', (0,5), (-1,-1), 0.25, colors.black),
            ('LINEABOVE', (0,-1),(-1,-1), 2.00, colors.black),

            # For top header
            ('SPAN', (0,0), (1,0)),
            ('BACKGROUND', (0,0), (-1,3), colors.lightblue),
            ('FONTNAME', (0,0), (-1,3), 'Courier-Bold'),
            ('FONTSIZE', (0,0), (-1,3), 10),
            ('FONTSIZE', (0,0), (1,1), 17),

        ]))
        whole_doc_elements.append(table_weekly_by_boro)
        whole_doc_elements.append(PageBreak())


        # ## Page 3
        header = ('Pothole Repairs: Fiscal Year per Borough', '', '', report_date_obj.strftime("%A, %B %#d, %Y"))
        dates_header_1 = ('From', fytd_start_str)
        dates_header_2 = ('To', report_date)
        fytd_start_obj = datetime.strptime(fytd_start_str, '%Y-%m-%d')
        dates_header_3 = ('Fiscal Year:', fytd_start_obj.year+1)
        # Should results in this: column_header = ('Operation', 'Bronx', 'Brooklyn', 'Manhattan', 'Queens', 'Staten Island', 'Operation Total')
        column_header = ['Operation']
        for each in unique_boro:
            column_header.append(each['boro_id__boro_long'])
        column_header.append('Operation Total')
        column_header = (column_header) # Convert to tuple, for immutability

        data = [
            header,
            '', # Empty row
            dates_header_1,
            dates_header_2,
            dates_header_3,
            column_header,
        ]

        body_data = []
        boro_i = 0
        boro_count = unique_boro.count()
        out_row = []
        holes_total = 0
        for each in fiscal_year_by_boro:
            # On first day of the tracking week, append boro operation info
            if boro_i == 0:
                out_row.append("{}".format(each['operation_id__operation']))

            holes_total += each['total_repaired'] if each['total_repaired'] is not None else 0
            out_row.append(each['total_repaired'] if each['total_repaired'] is not None else '')

            # 5 unique boro worth of data has been processed, save it, and reset variables
            if boro_i == boro_count-1:
                out_row.append(holes_total)
                out_row_tuple = (out_row)
                body_data.append(out_row_tuple)

                boro_i = 0
                out_row = []
                holes_total = 0
            else:
                boro_i += 1

        # Calculate Totals row (Last row of the table)
        bronx_total             = 0
        brooklyn_total          = 0
        manhattan_total         = 0
        queens_total            = 0
        staten_island_total     = 0
        operation_total_total   = 0
        for each in body_data:
            bronx_total             += each[1] if isinstance(each[1], int) else 0
            brooklyn_total          += each[2] if isinstance(each[2], int) else 0
            manhattan_total         += each[3] if isinstance(each[3], int) else 0
            queens_total            += each[4] if isinstance(each[4], int) else 0
            staten_island_total     += each[5] if isinstance(each[5], int) else 0
            operation_total_total   += each[6] if isinstance(each[6], int) else 0

        totals_tuple_row = (
            'Total'
            ,bronx_total
            ,brooklyn_total
            ,manhattan_total
            ,queens_total
            ,staten_island_total
            ,operation_total_total
        )
        body_data.append(totals_tuple_row)

        data = data + body_data # Concate the two list

        table_fiscal_year_by_boro = Table(
            data,
            colWidths=150
        )
        table_fiscal_year_by_boro.setStyle(TableStyle([
            ('BOX', (0,6), (-1,-1), 0.25, colors.black),
            ('INNERGRID', (0,6), (-1,-1), 0.25, colors.black),
            ('LINEABOVE', (0,-1),(-1,-1), 2.00, colors.black),

            # For top header
            ('SPAN', (0,0), (1,0)),
            ('BACKGROUND', (0,0), (-1,4), colors.lightblue),
            ('FONTNAME', (0,0), (-1,4), 'Courier-Bold'),
            ('FONTSIZE', (0,0), (-1,4), 10),
            ('FONTSIZE', (0,0), (1,1), 17),


        ]))
        whole_doc_elements.append(table_fiscal_year_by_boro)


        ## Build the doc
        doc.build(whole_doc_elements)

        # Move the read head to position 0, so when we call read(), it will read starting at the correct position
        buffer.seek(0)
        buffer_decoded = io.TextIOWrapper(buffer, encoding='utf-8', errors='ignore').read()


        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "pdf_bytes": buffer_decoded,
        })
    except ObjectDoesNotExist as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: GetPDFReport():\n\nError: {}. For '{}'".format(e, report_date),
        })
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: GetPDFReport():\n\nError: {}".format(e),
            # "post_msg": "DailyPothole: GetPDFReport():\n\nError: {}. The exception type is:{}".format(e,  e.__class__.__name__),
        })


def LookupPotholesAndCrewData(request):

    if request.method != "POST":
        return JsonResponse({
            "post_success": True,
            "post_msg": "{} HTTP request not supported".format(request.method),
        })


    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: LookupPotholesAndCrewData(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "LookupPotholesAndCrewData():\n\nUNAUTHENTICATE USER!",
            "post_data": None,
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: LookupPotholesAndCrewData():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    try:
        look_up_date    = json_blob['look_up_date']
        operation       = json_blob['operation']
        borough         = json_blob['borough']

        client_is_admin = user_is_active_admin(remote_user)["isAdmin"]

        ## Get the core data
        if client_is_admin:
            pass
        else:
            permission_obj = TblPermission.objects.using('DailyPothole').filter(
                user_id__username__exact=remote_user
                ,operation_id__operation__exact=operation
                ,boro_id__boro_long__exact=borough
            )

            if permission_obj.count() == 0:
                raise ValueError("'{}' does not have any permission for '{}' and '{}'".format(remote_user, operation, borough))

        pothole_and_crew_data = TblPotholeMaster.objects.using('DailyPothole').get( ## Do not apply special filtering rule for CW_RESURFACING, due to unwanted error message in the front end
            repair_date__exact=look_up_date,
            operation_id__operation__exact=operation,
            boro_id__boro_long__exact=borough,
        )

        repair_crew_count   = pothole_and_crew_data.repair_crew_count
        holes_repaired      = pothole_and_crew_data.holes_repaired
        daily_crew_count    = pothole_and_crew_data.daily_crew_count


        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "look_up_date": look_up_date,
            "repair_crew_count": repair_crew_count,
            "holes_repaired": holes_repaired,
            "daily_crew_count": daily_crew_count,
        })
    except ObjectDoesNotExist as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: LookupPotholesAndCrewData():\n\nError: {}. For '{}'".format(e, look_up_date),
        })
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: LookupPotholesAndCrewData():\n\nError: {}".format(e),
            # "post_msg": "DailyPothole: LookupPotholesAndCrewData():\n\nError: {}. The exception type is:{}".format(e,  e.__class__.__name__),
        })


class AdminPanelPageView(generic.ListView):
    template_name = 'DailyPothole.template.adminpanel.html'

    req_success = False
    err_msg = ""

    client_is_admin = False

    def get_queryset(self):
        # Check for Active Admins
        self.client_is_admin = user_is_active_admin(self.request.user)["isAdmin"]

        ## Get the core data
        try:
            if self.client_is_admin:
                complaints_data = TblComplaint.objects.none()
            else:
                raise ValueError("'{}' is not an Admin, and is not authorized to see this page.".format(self.request.user))

        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: AdminPanelPageView(): get_queryset(): {}".format(e)
            print(self.err_msg)
            return TblComplaint.objects.none()

        self.req_success = True
        return complaints_data

    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)

            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = self.client_is_admin
            return context
        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: AdminPanelPageView(): get_context_data(): {}".format(e)
            print(self.err_msg)

            context = super().get_context_data(**kwargs)
            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = False
            return context


class UsersPanelPageView(generic.ListView):
    template_name = 'DailyPothole.template.userspanel.html'
    context_object_name = 'users'

    req_success = False
    err_msg = ""

    client_is_admin = False

    def get_queryset(self):
        # Check for Active Admins
        self.client_is_admin = user_is_active_admin(self.request.user)["isAdmin"]

        ## Get the core data
        try:
            if self.client_is_admin:
                users_data = TblUser.objects.using('DailyPothole').all().order_by('username')
            else:
                raise ValueError("'{}' is not an Admin, and is not authorized to see this page.".format(self.request.user))

        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: UsersPanelPageView(): get_queryset(): {}".format(e)
            print(self.err_msg)
            return None

        self.req_success = True
        return users_data

    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)

            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = self.client_is_admin
            return context
        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: UsersPanelPageView(): get_context_data(): {}".format(e)
            print(self.err_msg)

            context = super().get_context_data(**kwargs)
            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = False
            return context


def AddUser(request):

    if request.method != "POST":
        return JsonResponse({
            "post_success": True,
            "post_msg": "{} HTTP request not supported".format(request.method),
        })


    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: AddUser(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "AddUser():\n\nUNAUTHENTICATE USER!",
            "post_data": None,
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: AddUser():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    try:
        username_input      = json_blob['username_input']
        is_admin_input      = json_blob['is_admin_input']


        is_admin = user_is_active_admin(remote_user)["isAdmin"]
        if not is_admin:
            raise ValueError("'{}' is not admin and does not have the permission to add a new user".format(remote_user))


        if username_input is None:
            raise ValueError("username_input cannot be null")

        if username_input == '':
            raise ValueError("username_input cannot be empty string")

        if is_admin_input is None:
            raise ValueError("is_admin_input cannot be null")

        if is_admin_input not in ['True', 'False']:
            raise ValueError("Unrecognized is_admin_input value '{}', must be either 'True' or 'False'".format(is_admin_input))


        try:
            new_user = TblUser(username=username_input, is_admin=is_admin_input)
            new_user.save(using='DailyPothole')
        except Exception as e:
            raise e

        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "user_id": new_user.user_id,
            "username": new_user.username,
            "is_admin": new_user.is_admin,
        })
    except ObjectDoesNotExist as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: AddUser():\n\nError: {}. For '{}'".format(e, username_input),
        })
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: AddUser():\n\nError: {}".format(e),
            # "post_msg": "DailyPothole: AddUser():\n\nError: {}. The exception type is:{}".format(e,  e.__class__.__name__),
        })


def UpdateUser(request):

    if request.method != "POST":
        return JsonResponse({
            "post_success": True,
            "post_msg": "{} HTTP request not supported".format(request.method),
        })


    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: UpdateUser(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "UpdateUser():\n\nUNAUTHENTICATE USER!",
            "post_data": None,
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: UpdateUser():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    try:
        table               = json_blob['table']
        column              = json_blob['column']


        is_admin = user_is_active_admin(remote_user)["isAdmin"]
        if not is_admin:
            raise ValueError("'{}' is not admin and does not have the permission to add a new user".format(remote_user))


        if table == 'tblUser' and column == 'IsAdmin':
            user_id             = json_blob['id']
            is_admin_input      = json_blob['new_value']
        else:
            raise ValueError("table '{}' and column '{}' is not recognized for this api".format(table, column))

        try:
            user_id = int(user_id)
        except Exception as e:
            raise ValueError("Cannot convert '{}' to int".format(user_id))

        if is_admin_input is None:
            raise ValueError("is_admin_input cannot be null")

        if is_admin_input not in ['True', 'False']:
            raise ValueError("Unrecognized is_admin_input value '{}', must be either 'True' or 'False'".format(is_admin_input))


        try:
            user = TblUser.objects.using("DailyPothole").get(user_id=user_id)
            user.is_admin = is_admin_input
            user.save(using='DailyPothole')
        except Exception as e:
            raise e

        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "user_id": user.user_id,
            "username": user.username,
            "is_admin": user.is_admin,
        })
    except ObjectDoesNotExist as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: UpdateUser():\n\nError: {}. For '{}' and '{}'".format(e, user_id, is_admin_input),
        })
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: UpdateUser():\n\nError: {}".format(e),
            # "post_msg": "DailyPothole: UpdateUser():\n\nError: {}. The exception type is:{}".format(e,  e.__class__.__name__),
        })


def DeleteUser(request):

    if request.method != "POST":
        return JsonResponse({
            "post_success": True,
            "post_msg": "{} HTTP request not supported".format(request.method),
        })


    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: DeleteUser(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "DeleteUser():\n\nUNAUTHENTICATE USER!",
            "post_data": None,
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: DeleteUser():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    try:
        user_id               = json_blob['user_id']

        is_admin = user_is_active_admin(remote_user)["isAdmin"]
        if not is_admin:
            raise ValueError("'{}' is not admin and does not have the permission to add a new user".format(remote_user))


        try:
            user_id = int(user_id)
        except Exception as e:
            raise ValueError("Cannot convert '{}' to int".format(user_id))


        try:
            user = TblUser.objects.using("DailyPothole").get(user_id=user_id)
            user.delete()
        except Exception as e:
            raise e

        return JsonResponse({
            "post_success": True,
            "post_msg": None,
        })
    except ObjectDoesNotExist as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: DeleteUser():\n\nError: {}. For '{}'".format(e, user_id),
        })
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: DeleteUser():\n\nError: {}".format(e),
            # "post_msg": "DailyPothole: DeleteUser():\n\nError: {}. The exception type is:{}".format(e,  e.__class__.__name__),
        })


class UserPermissionsPanelPageView(generic.ListView):
    template_name = 'DailyPothole.template.userpermissionspanel.html'
    context_object_name = 'user_permissions'

    req_success = False
    err_msg = ""

    user_list = []
    operation_list = []
    boro_list = []

    client_is_admin = False

    def get_queryset(self):
        # Check for Active Admins
        self.client_is_admin = user_is_active_admin(self.request.user)["isAdmin"]

        ## Get the core data
        try:
            if self.client_is_admin:
                user_permissions_data = TblPermission.objects.using('DailyPothole').all().order_by('user_id')
                self.user_list = [each.username for each in TblUser.objects.using('DailyPothole').all().order_by('username')]
                self.operation_list = [each.operation for each in TblOperation.objects.using('DailyPothole').all()]
                self.boro_list = [each.boro_long for each in TblBoro.objects.using('DailyPothole').all()]
            else:
                raise ValueError("'{}' is not an Admin, and is not authorized to see this page.".format(self.request.user))

        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: UserPermissionsPanelPageView(): get_queryset(): {}".format(e)
            print(self.err_msg)
            return None

        self.req_success = True
        return user_permissions_data

    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)

            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["user_list"] = self.user_list
            context["operation_list"] = self.operation_list
            context["boro_list"] = self.boro_list

            context["client_is_admin"] = self.client_is_admin
            return context
        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: UserPermissionsPanelPageView(): get_context_data(): {}".format(e)
            print(self.err_msg)

            context = super().get_context_data(**kwargs)
            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["operation_list"] = []
            context["boro_list"] = []


            context["client_is_admin"] = False
            return context


def AddUserPermission(request):

    if request.method != "POST":
        return JsonResponse({
            "post_success": True,
            "post_msg": "{} HTTP request not supported".format(request.method),
        })


    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: AddUserPermission(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "AddUserPermission():\n\nUNAUTHENTICATE USER!",
            "post_data": None,
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: AddUserPermission():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    try:
        username_input      = json_blob['username_input']
        operation_input     = json_blob['operation_input']
        boro_input          = json_blob['boro_input']


        is_admin = user_is_active_admin(remote_user)["isAdmin"]
        if not is_admin:
            raise ValueError("'{}' is not admin and does not have the permission to add a new user".format(remote_user))


        if username_input is None:
            raise ValueError("username_input cannot be null")

        if username_input == '':
            raise ValueError("username_input cannot be empty string")

        if operation_input is None:
            raise ValueError("operation_input cannot be null")

        if operation_input == '':
            raise ValueError("operation_input cannot be empty string")

        if boro_input is None:
            raise ValueError("boro_input cannot be null")

        if boro_input == '':
            raise ValueError("boro_input cannot be empty string")



        try:
            user = TblUser.objects.using("DailyPothole").get(username=username_input)
            operation = TblOperation.objects.using("DailyPothole").get(operation=operation_input)
            boro = TblBoro.objects.using("DailyPothole").get(boro_long=boro_input)

            new_permission = TblPermission(
                user_id=user
                ,operation_id=operation
                ,boro_id=boro
            )
            new_permission.save(using='DailyPothole')
        except Exception as e:
            raise e

        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "permission_id": new_permission.permission_id,
            "username": new_permission.user_id.username,
            "operation": new_permission.operation_id.operation,
            "boro_long": new_permission.boro_id.boro_long,
        })
    except ObjectDoesNotExist as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: AddUserPermission():\n\nError: {}. For '{}'".format(e, username_input),
        })
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: AddUserPermission():\n\nError: {}".format(e),
            # "post_msg": "DailyPothole: AddUserPermission():\n\nError: {}. The exception type is:{}".format(e,  e.__class__.__name__),
        })


def UpdateUserPermission(request):

    if request.method != "POST":
        return JsonResponse({
            "post_success": True,
            "post_msg": "{} HTTP request not supported".format(request.method),
        })


    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: UpdateUserPermission(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "UpdateUserPermission():\n\nUNAUTHENTICATE USER!",
            "post_data": None,
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: UpdateUserPermission():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    try:
        table               = json_blob['table']
        column              = json_blob['column']


        is_admin = user_is_active_admin(remote_user)["isAdmin"]
        if not is_admin:
            raise ValueError("'{}' is not admin and does not have the permission to add a new user".format(remote_user))


        if  (
                ( table == 'tblUser' and column == 'Username' )
                or ( table == 'tblOperation' and column == 'Operation' )
                or ( table == 'tblBoro' and column == 'BoroLong' )
            ):
            permission_id   = json_blob['id']
            new_value       = json_blob['new_value']
        else:
            raise ValueError("table '{}' and column '{}' is not recognized for this api".format(table, column))

        try:
            permission_id = int(permission_id)
        except Exception as e:
            raise ValueError("Cannot convert '{}' to int".format(permission_id))

        if new_value is None:
            raise ValueError("new_value cannot be null")

        if new_value == '':
            raise ValueError("new_value cannot be empty string")


        try:
            permission = TblPermission.objects.using("DailyPothole").get(permission_id=permission_id)
            if table == 'tblUser' and column == 'Username':
                user = TblUser.objects.using("DailyPothole").get(username=new_value)
                permission.user_id = user
            if table == 'tblOperation' and column == 'Operation':
                operation = TblOperation.objects.using("DailyPothole").get(operation=new_value)
                permission.operation_id = operation
            if table == 'tblBoro' and column == 'BoroLong':
                boro = TblBoro.objects.using("DailyPothole").get(boro_long=new_value)
                permission.boro_id = boro

            permission.save(using='DailyPothole')
        except Exception as e:
            raise e

        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "username": permission.user_id.username,
            "operation": permission.operation_id.operation,
            "boro_long": permission.boro_id.boro_long,
        })
    except ObjectDoesNotExist as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: UpdateUserPermission():\n\nError: {}. For '{}' and '{}'".format(e, permission_id, new_value),
        })
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: UpdateUserPermission():\n\nError: {}".format(e),
            # "post_msg": "DailyPothole: UpdateUserPermission():\n\nError: {}. The exception type is:{}".format(e,  e.__class__.__name__),
        })


def DeleteUserPermission(request):

    if request.method != "POST":
        return JsonResponse({
            "post_success": True,
            "post_msg": "{} HTTP request not supported".format(request.method),
        })


    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: DeleteUserPermission(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "DeleteUserPermission():\n\nUNAUTHENTICATE USER!",
            "post_data": None,
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: DeleteUserPermission():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    try:
        permission_id               = json_blob['permission_id']

        is_admin = user_is_active_admin(remote_user)["isAdmin"]
        if not is_admin:
            raise ValueError("'{}' is not admin and does not have the permission to add a new user".format(remote_user))


        try:
            permission_id = int(permission_id)
        except Exception as e:
            raise ValueError("Cannot convert '{}' to int".format(permission_id))


        try:
            permission = TblPermission.objects.using("DailyPothole").get(permission_id=permission_id)
            permission.delete()
        except Exception as e:
            raise e

        return JsonResponse({
            "post_success": True,
            "post_msg": None,
        })
    except ObjectDoesNotExist as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: DeleteUserPermission():\n\nError: {}. For '{}'".format(e, permission_id),
        })
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: DeleteUserPermission():\n\nError: {}".format(e),
            # "post_msg": "DailyPothole: DeleteUserPermission():\n\nError: {}. The exception type is:{}".format(e,  e.__class__.__name__),
        })


class CsvExportPageView(generic.ListView):
    template_name = 'DailyPothole.template.csvexport.html'
    context_object_name = 'complaints'

    req_success = False
    err_msg = ""

    client_is_admin = False
    operation_list = []

    def get_queryset(self):
        # Check for Active Admins
        self.client_is_admin = user_is_active_admin(self.request.user)["isAdmin"]

        ## Get the core data
        try:
            if self.client_is_admin:
                complaints_data = TblComplaint.objects.none()
            else:
                raise ValueError("'{}' is not an Admin, and is not authorized to see this page.".format(self.request.user))

            self.operation_list = [each.operation for each in TblOperation.objects.using('DailyPothole').all()]

        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: CsvExportPageView(): get_queryset(): {}".format(e)
            print(self.err_msg)
            return TblComplaint.objects.none()

        self.req_success = True
        return complaints_data

    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)

            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = self.client_is_admin
            context["operation_list"] = self.operation_list
            return context
        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: CsvExportPageView(): get_context_data(): {}".format(e)
            print(self.err_msg)

            context = super().get_context_data(**kwargs)
            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = False
            context["operation_list"] = []
            return context


def GetCsvExport(request):
    if request.method != "POST":
        return JsonResponse({
            "post_success": True,
            "post_msg": "{} HTTP request not supported".format(request.method),
        })


    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: GetCsvExport(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "GetCsvExport():\n\nUNAUTHENTICATE USER!",
            "post_data": None,
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: GetCsvExport():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    try:
        import csv
        from io import StringIO
        dummy_in_mem_file = StringIO()

        start_date      = json_blob['start_date']
        end_date        = json_blob['end_date']
        operation_list  = json_blob['operation_list']
        type_of_query   = json_blob['type_of_query']

        is_admin = user_is_active_admin(remote_user)["isAdmin"]
        if not is_admin:
            raise ValueError("'{}' is not admin. Only admins can access the GetCsvExport() api".format(remote_user))

        from django.db.models import Sum, Max
        from datetime import datetime, timedelta
        from dateutil import relativedelta
        from itertools import chain
        from operator import attrgetter

        if type_of_query == 'date_range_summary':
            if datetime.strptime(start_date, '%Y-%m-%d') > datetime.strptime(end_date, '%Y-%m-%d'):
                raise ValueError(f"start date {start_date} is greater than end date {end_date}")

            ## Initial filtering
            potholes_data = TblPotholeMaster.objects.using('DailyPothole')
            potholes_data = filter_out_excluded_operation_boro(potholes_data)
            if len(operation_list) != 0:
                potholes_data = potholes_data.filter(
                    operation_id__operation__in=operation_list,
                )
            potholes_data = potholes_data.filter(
                repair_date__range=[start_date, end_date],
            ).values(
                'boro_id__boro_code'
            ).annotate(
                total_crew_count=Sum('repair_crew_count')
                ,total_repaired=Sum('holes_repaired')
            ).order_by('boro_id__boro_order')

            ## Post calculation
            crew_count_sum = 0
            pothole_repaired_sum = 0
            for each in potholes_data:
                crew_count_sum += each['total_crew_count']
                pothole_repaired_sum += each['total_repaired']

            ## Create the csv
            writer = csv.writer(dummy_in_mem_file)
            writer.writerow(['Date Range: {} to {}'.format(start_date, end_date)])
            writer.writerow(['BORO_CODE', 'SumOfREPAIR_CREW_COUNT', 'SumOfTOTAL_POTHOLES'])

            for each in potholes_data:
                eachrow = [
                    each['boro_id__boro_code']
                    ,each['total_crew_count']
                    ,each['total_repaired']
                ]
                writer.writerow(eachrow)

            writer.writerow(['Total', crew_count_sum, pothole_repaired_sum])

        elif type_of_query == 'ytd_range_last_five_years_summary':
            today = datetime.today()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')

            if today.year != end_date_obj.year:
                raise ValueError(f"EndDate ({ end_date }) is not in current Calendar Year. Please give a date in { today.year }")

            year_1_start = f'{ today.year }-01-01'
            year_2_start = f'{ today.year-1 }-01-01'
            year_3_start = f'{ today.year-2 }-01-01'
            year_4_start = f'{ today.year-3 }-01-01'
            year_5_start = f'{ today.year-4 }-01-01'

            year_1_end = f'{ today.year   }-{ end_date_obj.month }-{ end_date_obj.day }'
            year_2_end = f'{ today.year-1 }-{ end_date_obj.month }-{ end_date_obj.day }'
            year_3_end = f'{ today.year-2 }-{ end_date_obj.month }-{ end_date_obj.day }'
            year_4_end = f'{ today.year-3 }-{ end_date_obj.month }-{ end_date_obj.day }'
            year_5_end = f'{ today.year-4 }-{ end_date_obj.month }-{ end_date_obj.day }'


            potholes_data = TblPotholeMaster.objects.using('DailyPothole').filter(
                Q(repair_date__range=[year_1_start, year_1_end])
                | Q(repair_date__range=[year_2_start, year_2_end])
                | Q(repair_date__range=[year_3_start, year_3_end])
                | Q(repair_date__range=[year_4_start, year_4_end])
                | Q(repair_date__range=[year_5_start, year_5_end])
            )
            potholes_data = filter_out_excluded_operation_boro(potholes_data)
            if len(operation_list) != 0:
                potholes_data = potholes_data.filter(
                    operation_id__operation__in=operation_list,
                )


            by_year_sum = potholes_data.values(
                'repair_date__year'
            ).annotate(
                max_repair_date=Max('repair_date')
                ,total_crew_count=Sum('repair_crew_count')
                ,total_repaired=Sum('holes_repaired')
            ).order_by(
                'repair_date__year'
            )

            writer = csv.writer(dummy_in_mem_file)
            row_header = ['Calendar Year To Date as of:']
            crew_row_list = ['Crews']
            for each in by_year_sum:
                row_header.append(each['max_repair_date'])
                crew_row_list.append(each['total_crew_count'])
            writer.writerow(row_header)
            writer.writerow(crew_row_list)
            writer.writerow([''])

            by_year_boro_sum = potholes_data.values(
                'repair_date__year'
                ,'boro_id__boro_long'
            ).annotate(
                total_repaired=Sum('holes_repaired')
            ).order_by(
                'boro_id__boro_long'
                ,'repair_date__year'
            )


            writer.writerow(['Potholes'])
            ordered_boro_long_list = list(by_year_boro_sum.order_by('boro_id__boro_long').values_list('boro_id__boro_long', flat=True).distinct())
            for each in ordered_boro_long_list:
                pothole_fixed_row_list = []
                pothole_fixed_row_list.append(each)

                for each_row in by_year_boro_sum.filter(boro_id__boro_long=each):
                    pothole_fixed_row_list.append(each_row['total_repaired'])

                writer.writerow(pothole_fixed_row_list)


            pothole_fixed_year_summary_row = ['Total']

            for each in by_year_sum.order_by('repair_date__year'):
                pothole_fixed_year_summary_row.append(each['total_repaired'])

            writer.writerow(pothole_fixed_year_summary_row)

        elif type_of_query == 'fytd_n_last_week_wo_art_maint':
            today = datetime.today()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')

            if end_date_obj > today:
                raise ValueError(f"EndDate { end_date } is in the future. Please give a date before or equal to { today.strftime('%Y-%m-%d') }")

            ## Assuming a new FY starts at July 1st
            fytd_start_str = "{}-07-01".format(end_date_obj.year - 1 if end_date_obj.month < 7 else end_date_obj.year)

            ## Get the previous week's Sunday from a given date
            def prior_week_end(d):
                ## If given date is sunday, return last week's sunday
                if d.isoweekday() == 7:
                    return d - timedelta(days=7)
                else:
                    ## isoweekday() returns the day of the week as an integer, where Monday is 1 and Sunday is 7
                    return d - timedelta(days=(d.isoweekday() % 7 ))

            ## Get the previous week's Monday from a given date
            def prior_week_start(d):
                ## subtract 6 days from sunday
                return prior_week_end(d) - timedelta(days=6)

            last_week_monday = (prior_week_end(end_date_obj) - timedelta(days=6))
            last_week_sunday = (prior_week_end(end_date_obj)                    )

            from django.db import connections
            with connections['DailyPothole'].cursor() as cursor:
                cte_base_query = f"""
                    WITH base AS (
                        SELECT
                            tblPotholeMaster.[RepairDate]
                            ,tblPotholeMaster.[ActualCrewCount]
                            ,tblPotholeMaster.[ActualPotholesRepaired]
                            ,tblOperation.[Operation]
                            ,tblBoro.[BoroCode]
                            ,tblBoro.[BoroOrder]
                            ,tblBoro.[BoroLong]
                        FROM tblPotholeMaster
                        LEFT JOIN tblOperation
                        ON tblPotholeMaster.[OperationId] = tblOperation.[OperationId]
                        LEFT JOIN tblBoro
                        ON tblPotholeMaster.[BoroId] = tblBoro.[BoroId]
                        WHERE (
                            {get_excluded_operation_boro_as_where_cond()}
                            AND tblOperation.[Operation] <> 'ARTERIAL MAINTENANCE'
                        )
                    )

                    ,fytd AS (
                        SELECT
                            [RepairDate]
                            ,[ActualCrewCount]
                            ,[ActualPotholesRepaired]
                            ,[Operation]
                            ,[BoroCode]
                            ,[BoroOrder]
                            ,[BoroLong]
                        FROM base
                        WHERE
                            [RepairDate] >= '{fytd_start_str}' AND [RepairDate] <= '{end_date}'
                    )

                    ,last_week AS (
                        SELECT
                            [RepairDate]
                            ,[ActualCrewCount]
                            ,[ActualPotholesRepaired]
                            ,[Operation]
                            ,[BoroCode]
                            ,[BoroOrder]
                            ,[BoroLong]
                        FROM base
                        WHERE
                            [RepairDate] >= '{last_week_monday.strftime('%Y-%m-%d')}' AND [RepairDate] <= '{last_week_sunday.strftime('%Y-%m-%d')}'
                    )

                    ,summary AS (
                        SELECT
                            fytd_grouped.[BoroCode_fytd]                    AS [boro_code_fytd]
                            ,fytd_grouped.[ActualCrewCount_fytd]            AS [total_crew_count_fytd]
                            ,fytd_grouped.[ActualPotholesRepaired_fytd]     AS [total_repaired_fytd]
                            ,lwk_grouped.[ActualCrewCount_lwk]              AS [total_crew_count_lwk]
                            ,lwk_grouped.[ActualPotholesRepaired_lwk]       AS [total_repaired_lwk]
                        FROM (
                            SELECT
                                [BoroCode]                      AS [BoroCode_fytd]
                                ,SUM([ActualCrewCount])         AS [ActualCrewCount_fytd]
                                ,SUM([ActualPotholesRepaired])  AS [ActualPotholesRepaired_fytd]
                            FROM fytd
                            GROUP BY [BoroCode]
                        ) AS fytd_grouped
                        LEFT JOIN (
                            SELECT
                                [BoroCode]                      AS [BoroCode_lwk]
                                ,SUM([ActualCrewCount])         AS [ActualCrewCount_lwk]
                                ,SUM([ActualPotholesRepaired])  AS [ActualPotholesRepaired_lwk]
                            FROM last_week
                            GROUP BY [BoroCode]
                        ) AS lwk_grouped
                        ON fytd_grouped.[BoroCode_fytd] = lwk_grouped.[BoroCode_lwk]
                    )
                """

                summary_query = f"""
                    {cte_base_query}

                    SELECT
                        summary.[boro_code_fytd]
                        ,summary.[total_crew_count_fytd]
                        ,summary.[total_repaired_fytd]
                        ,summary.[total_crew_count_lwk]
                        ,summary.[total_repaired_lwk]
                        ,tblBoro.[BoroOrder]
                        ,tblBoro.[BoroLong]
                    FROM summary
                    LEFT JOIN tblBoro
                    ON summary.[boro_code_fytd] = tblBoro.[BoroCode]
                    ORDER BY tblBoro.[BoroOrder]
                """

                total_query = f"""
                    {cte_base_query}

                    SELECT
                        SUM([total_crew_count_fytd])    AS [sum_crew_count_fytd]
                        ,SUM([total_repaired_fytd])     AS [sum_repaired_fytd]
                        ,SUM([total_crew_count_lwk])    AS [sum_crew_count_lwk]
                        ,SUM([total_repaired_lwk])      AS [sum_repaired_lwk]
                    FROM summary
                """

                cursor.execute(summary_query)

                ## Return all rows from a cursor as a dict
                columns = [col[0] for col in cursor.description]
                no_art_maint_summary =  [
                    dict(zip(columns, row))
                    for row in cursor.fetchall()
                ]

                cursor.execute(total_query)

                ## Return all rows from a cursor as a dict
                columns = [col[0] for col in cursor.description]
                no_art_maint_total =  [
                    dict(zip(columns, row))
                    for row in cursor.fetchall()
                ]

            ## Create the csv
            writer = csv.writer(dummy_in_mem_file)
            writer.writerow([end_date_obj.strftime("%A, %B %d, %Y") , ''    , ''])
            writer.writerow(['Potholes Repaired'                    , ''    , ''])
            writer.writerow(['Borough'                              , 'FYTD', f'{last_week_monday.strftime("%m/%d/%y")} - {last_week_sunday.strftime("%m/%d/%y")} Activity'])
            for each in no_art_maint_summary:
                eachrow = [
                    each['BoroLong']
                    ,each['total_repaired_fytd']
                    ,each['total_repaired_lwk']
                ]
                writer.writerow(eachrow)
            writer.writerow(['Total',  no_art_maint_total[0]['sum_repaired_fytd']  , no_art_maint_total[0]['sum_repaired_lwk']])
            writer.writerow([''     , ''                        , ''])
            writer.writerow(['Crews:', no_art_maint_total[0]['sum_crew_count_fytd'], no_art_maint_total[0]['sum_crew_count_lwk']])

        else:
            raise ValueError("Unknown value for type_of_query: '{}'".format(type_of_query))


        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "post_csv_bytes": dummy_in_mem_file.getvalue(),
        })
    except ObjectDoesNotExist as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: GetCsvExport():\n\nError: {}. For '{}'".format(e, start_date),
        })
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "DailyPothole: GetCsvExport():\n\nError: {}".format(e),
            # "post_msg": "DailyPothole: GetCsvExport():\n\nError: {}. The exception type is:{}".format(e,  e.__class__.__name__),
        })


