from django.shortcuts import render
from django.views.generic import TemplateView
from django.views import generic
from django.http import HttpResponse, JsonResponse
from .models import *
from django.db.models import Min, Q
import json


## Check if remote user is admin and is active
def user_is_active_admin(username):
    try:
        admin_query = TblAdmins.objects.using('OrgChartWrite').filter(
            windows_username=username,
            active=True, ## Filters for active Admins
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
    template_name = 'OrgChartPortal.template.home.html'
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
    template_name = 'OrgChartPortal.template.about.html'


class ContactPageView(TemplateView):
    template_name = 'OrgChartPortal.template.contact.html'


def get_allowed_list_of_wu(username):
    try:
        wu_query = TblPermissions.objects.using('OrgChartRead').filter(
            windows_username=username,
        ).order_by('wu')

        if wu_query.count() > 0:
            return {
                "success": True,
                "err": "",
                "wu_list": [each.wu.wu for each in wu_query],
            }
        return {
            "success": False,
            "err": "Cannot find any WU permissions for '{}'".format(username),
        }
    except Exception as e:
        print("Exception: OrgChartPortal: get_allowed_list_of_wu(): {}".format(e))
        return {
            "success": False,
            "err": 'Exception: OrgChartPortal: get_allowed_list_of_wu(): {}'.format(e),
        }


class EmpGridPageView(generic.ListView):
    template_name = 'OrgChartPortal.template.empgrid.html'
    context_object_name = 'emp_entries'

    req_success = False
    err_msg = ""

    client_is_admin = False

    ## TODO Implement Admin in database
    # def get_queryset(self):
    #     ## Check for Active Admins
    #     # is_active_admin = user_is_active_admin(self.request.user)
    #     # if is_active_admin["success"] == True:
    #     #     self.client_is_admin = True
    #     # else:
    #     #     self.req_success = False

    #     ## Get the core data
    #     try:
    #         if self.client_is_admin:
    #             pms_entries = TblEmployees.objects.using('OrgChartRead').all().order_by('wu')
    #         else:
    #             allowed_wu_list_obj = get_allowed_list_of_wu(self.request.user)
    #             if allowed_wu_list_obj['success'] == False:
    #                 raise ValueError(f"get_allowed_list_of_wu() failed: {allowed_wu_list_obj['err']}")
    #             else:
    #                 allowed_wu_list = allowed_wu_list_obj['wu_list']

    #             pms_entries = TblEmployees.objects.using('OrgChartRead').filter(
    #                 wu__in=allowed_wu_list,
    #             ).order_by('wu')
    #     except Exception as e:
    #         self.req_success = False
    #         self.err_msg = "Exception: EmpGridPageView(): get_queryset(): {}".format(e)
    #         print(self.err_msg)
    #         return TblEmployees.objects.none()

    #     self.req_success = True
    #     return pms_entries

    def get_queryset(self):
        ## Check for Active Admins
        # is_active_admin = user_is_active_admin(self.request.user)
        # if is_active_admin["success"] == True:
        #     self.client_is_admin = True
        # else:
        #     self.client_is_admin = False

        ## Get the core data
        try:
            if self.client_is_admin:
                emp_entries = TblEmployees.objects.using('OrgChartRead').all().order_by('wu')
            else:
                allowed_wu_list_obj = get_allowed_list_of_wu(self.request.user)
                if allowed_wu_list_obj['success'] == False:
                    raise ValueError(f"get_allowed_list_of_wu() failed: {allowed_wu_list_obj['err']}")
                else:
                    allowed_wu_list = allowed_wu_list_obj['wu_list']

                emp_entries = TblEmployees.objects.using('OrgChartRead').filter(
                    pms__wu__in=allowed_wu_list,
                ).order_by('pms__wu')
        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: EmpGridPageView(): get_queryset(): {}".format(e)
            print(self.err_msg)
            return None

        self.req_success = True
        return emp_entries

    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)

            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = self.client_is_admin
            return context
        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: get_context_data(): {}".format(e)
            print(self.err_msg)

            context = super().get_context_data(**kwargs)
            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = False
            return context


def GetClientWUPermissions(request):
    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: OrgChartPortal: GetClientWUPermissions(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "OrgChartPortal: GetClientWUPermissions():\n\nUNAUTHENTICATE USER!",
        })

    ## Get the data
    try:
        wu_permissions_query = TblPermissions.objects.using('OrgChartRead').filter(
                windows_username=remote_user
            ).order_by('wu__wu')

        wu_permissions_list_json = list(wu_permissions_query.values('wu__wu', 'wu__wu_desc', 'wu__subdiv'))

        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "post_data": wu_permissions_list_json,
        })
    except Exception as e:
        err_msg = "Exception: OrgChartPortal: GetClientWUPermissions(): {}".format(e)
        print(err_msg)
        return JsonResponse({
            "post_success": False,
            "post_msg": err_msg
        })


def GetClientTeammates(request):
    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: OrgChartPortal: GetClientTeammates(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "OrgChartPortal: GetClientTeammates():\n\nUNAUTHENTICATE USER!",
        })

    ## Get the data
    try:
        wu_permissions_query = TblPermissions.objects.using('OrgChartRead').filter(
                windows_username=remote_user
            ).order_by('wu__wu')

        wu_permissions_list_json = wu_permissions_query.values('wu__wu')

        teammates_query = TblPermissions.objects.using('OrgChartRead').filter(
                wu__wu__in=wu_permissions_list_json
            ).order_by('pms__pms')

        teammates_list_json = list(teammates_query.values('pms__pms').annotate(pms__first_name=Min('pms__first_name'), pms__last_name=Min('pms__last_name')))

        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "post_data": teammates_list_json,
        })
    except Exception as e:
        err_msg = "Exception: OrgChartPortal: GetClientTeammates(): {}".format(e)
        print(err_msg)
        return JsonResponse({
            "post_success": False,
            "post_msg": err_msg
        })


def GetEmpGridStats(request):
    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: OrgChartPortal: GetEmpGridStats(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "OrgChartPortal: GetEmpGridStats():\n\nUNAUTHENTICATE USER!",
        })

    ## Get the data
    try:
        # teammates_list_json = list(teammates_query.values('pms__pms').annotate(pms__first_name=Min('pms__first_name'), pms__last_name=Min('pms__last_name')))

        allowed_wu_list_obj = get_allowed_list_of_wu(remote_user)
        if allowed_wu_list_obj['success'] == False:
            raise ValueError(f"get_allowed_list_of_wu() failed: {allowed_wu_list_obj['err']}")
        else:
            allowed_wu_list = allowed_wu_list_obj['wu_list']

        client_orgchart_data = TblEmployees.objects.using('OrgChartRead').filter(
            wu__in=allowed_wu_list,
        ).order_by('wu')

        emp_grid_stats_list_json = list(client_orgchart_data.values('pms').annotate(pms__first_name=Min('first_name'), pms__last_name=Min('last_name')))














        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "post_data": emp_grid_stats_list_json,
        })
    except Exception as e:
        err_msg = "Exception: OrgChartPortal: GetEmpGridStats(): {}".format(e)
        print(err_msg)
        return JsonResponse({
            "post_success": False,
            "post_msg": err_msg
        })


class OrgChartPageView(generic.ListView):
    template_name = 'OrgChartPortal.template.orgchart.html'
    context_object_name = 'emp_entries'

    req_success = False
    err_msg = ""

    client_is_admin = False

    def get_queryset(self):
        ## Check for Active Admins
        is_active_admin = user_is_active_admin(self.request.user)
        if is_active_admin["isAdmin"] == True:
            self.client_is_admin = True
        else:
            self.client_is_admin = False

        ## Get the core data
        try:
            if self.client_is_admin == False:
                return None
        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: EmpGridPageView(): get_queryset(): {}".format(e)
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
            return context
        except Exception as e:
            self.req_success = False
            self.err_msg = "Exception: get_context_data(): {}".format(e)
            print(self.err_msg)

            context = super().get_context_data(**kwargs)
            context["req_success"] = self.req_success
            context["err_msg"] = self.err_msg

            context["client_is_admin"] = False
            return context


def GetEmpCsv(request):
    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: OrgChartPortal: GetEmpCsv(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "OrgChartPortal: GetEmpCsv():\n\nUNAUTHENTICATE USER!",
        })

    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "OrgChartPortal: GetEmpCsv():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    ## Get the data
    try:
        active_lv_list = ['B', 'C', 'K', 'M', 'N', 'Q', 'R', 'S']
        root_pms = json_blob['root_pms']

        ## Check for Active Admins
        is_admin = user_is_active_admin(remote_user)["isAdmin"]

        emp_data = TblEmployees.objects.using('OrgChartRead').exclude(
            Q(supervisor_pms__isnull=True) | Q(supervisor_pms__exact='')
            ,~Q(pms__exact=root_pms) # our very top root_pms will have a null supervisor_pms, so this condition is to include the top root_pms despite the first exclude condition
        ).filter(
            lv__in=active_lv_list
        ).order_by(
            'supervisor_pms'
        )

        flat_all_row_dict = emp_data.values( # Returns a query set that returns dicts. MUCH faster than going though emp_data in a for loop (53 secs down to 350ms).
            "pms"
            ,"last_name"
            ,"first_name"
            ,"office_title"
            ,"civil_title"
            ,"wu__wu_desc"
            ,"supervisor_pms"
        )


        # Add allowed WU filter to queryset since client is not admin
        if not is_admin:
            #raise ValueError(f"'{remote_user}' is not admin. Only admins can access the GetEmpCsv() api")
            allowed_wu_list_obj = get_allowed_list_of_wu(remote_user)
            if allowed_wu_list_obj['success'] == False:
                raise ValueError(f"get_allowed_list_of_wu() failed: {allowed_wu_list_obj['err']}")
            else:
                allowed_wu_list = allowed_wu_list_obj['wu_list']

            emp_data = emp_data.filter(
                Q(wu__in=allowed_wu_list)
            )

        # If admin, flat_allowed_row_dict will be the same as flat_all_row_dict, else len(flat_allowed_row_dict) < len(flat_all_row_dict)
        flat_allowed_row_dict = emp_data.values(
            "pms"
            ,"last_name"
            ,"first_name"
            ,"office_title"
            ,"civil_title"
            ,"wu__wu_desc"
            ,"supervisor_pms"
        )


        ## Build a dict of emp pms and a dict of its emp info
        ##  {
        ##      "1234566":
        ##          {
        ##              "pms":              "1234567"
        ##              "last_name":        "john"
        ##              "first_name":       "doe"
        ##              "supervisor_pms":   "7654321"
        ##          }
        ##      ,"7654321": {...}
        ##      .
        ##      .
        ##      .
        ##  }
        flat_all_processed_dict = {}
        for each in flat_all_row_dict:
            each_emp_dict = {}

            each_emp_dict[f"pms"]                   = f"{each['pms']}"              .strip() if each['pms']             is not None else None
            each_emp_dict[f"last_name"]             = f"{each['last_name']}"        .strip() if each['last_name']       is not None else None
            each_emp_dict[f"first_name"]            = f"{each['first_name']}"       .strip() if each['first_name']      is not None else None
            each_emp_dict[f"office_title"]          = f"{each['office_title']}"     .strip() if each['office_title']    is not None else None
            each_emp_dict[f"civil_title"]           = f"{each['civil_title']}"      .strip() if each['civil_title']     is not None else None
            each_emp_dict[f"wu_desc"]               = f"{each['wu__wu_desc']}"      .strip() if each['wu__wu_desc']     is not None else None
            each_emp_dict[f"supervisor_pms"]        = f"{each['supervisor_pms']}"   .strip() if each['supervisor_pms']  is not None else None
            each_emp_dict["is_needed_to_hit_root"]  = False

            flat_all_processed_dict[f"{each['pms']}".strip()] = each_emp_dict

        flat_allowed_processed_dict = {}
        for each in flat_allowed_row_dict:
            each_emp_dict = {}

            each_emp_dict[f"pms"]                   = f"{each['pms']}"              .strip() if each['pms']             is not None else None
            each_emp_dict[f"last_name"]             = f"{each['last_name']}"        .strip() if each['last_name']       is not None else None
            each_emp_dict[f"first_name"]            = f"{each['first_name']}"       .strip() if each['first_name']      is not None else None
            each_emp_dict[f"office_title"]          = f"{each['office_title']}"     .strip() if each['office_title']    is not None else None
            each_emp_dict[f"civil_title"]           = f"{each['civil_title']}"      .strip() if each['civil_title']     is not None else None
            each_emp_dict[f"wu_desc"]               = f"{each['wu__wu_desc']}"      .strip() if each['wu__wu_desc']     is not None else None
            each_emp_dict[f"supervisor_pms"]        = f"{each['supervisor_pms']}"   .strip() if each['supervisor_pms']  is not None else None

            flat_allowed_processed_dict[f"{each['pms']}".strip()] = each_emp_dict


        ## Only marks and add the nodes between leaf and root, including root. This does not mark and add the leaf nodes themself!
        def TraverseToRootAndMark(pms, nodes_away_from_leaf):
            ## pms is root_pms, so lineage is reachable to root_pms, return true
            if pms == root_pms:
                return True

            ## pms is a root that's not root_pms, so lineage is not reachable to root_pms, return false
            if pms == '' or pms is None:
                return False

            ## pms is not a root, check its parent
            try:
                parent_pms = flat_all_processed_dict[pms]['supervisor_pms']
            except KeyError:
                parent_pms = None

            ## If can reach root, mark the given parent pms as needed
            can_reach_root = TraverseToRootAndMark( pms=parent_pms, nodes_away_from_leaf=nodes_away_from_leaf+1 )
            if can_reach_root:
                flat_all_processed_dict[parent_pms]["is_needed_to_hit_root"] = True
                ## nodes_away_from_leaf == 0 means that the caller is a leaf node, and should mark the calling pms as needed.
                ## This is needed because the above line of code only mark a parent as needed, not the caller, so that means the caller will be miseed in the marking process
                if nodes_away_from_leaf == 0:
                    flat_all_processed_dict[pms]["is_needed_to_hit_root"] = True
            return can_reach_root


        ## For each node in the allowed dataset, mark its path of nodes needed to reach to the root as "Needed".
        for emp_pms in flat_allowed_processed_dict:
            emp = flat_allowed_processed_dict[emp_pms]
            TraverseToRootAndMark( pms=emp['pms'], nodes_away_from_leaf=0 )


        allowed_and_needed_nodes_dict = {}
        for key, value in flat_all_processed_dict.items():
            if value["is_needed_to_hit_root"] == True:
                allowed_and_needed_nodes_dict[key] = value


        if len(allowed_and_needed_nodes_dict) == 0:
            if not is_admin:
                raise ValueError(f"Found no orgchart data with the following client permission(s): {allowed_wu_list}")
            else:
                raise ValueError(f"Found no orgchart data despite client being an admin")


        import csv
        from io import StringIO
        dummy_in_mem_file = StringIO()

        ## Create the csv
        writer = csv.writer(dummy_in_mem_file)
        writer.writerow(["pms", "sup_pms", "last_name", "first_name", "office_title", "civil_title", "wu_desc"]) # For reference to what to name your id and parent id column: https://github.com/bumbeishvili/org-chart/issues/88
        # writer.writerow(["last_name", "first_name", "id", "parentId"])

        for each in allowed_and_needed_nodes_dict:
            try:
                ## In the case that root_pms is not the actual top root of the entire org tree, but it's a middle node somewhere, we need to set that emp's sup_pms to empty string
                if allowed_and_needed_nodes_dict[each]['pms'] == root_pms:
                    sup_pms = ""
                else:
                    sup_pms = allowed_and_needed_nodes_dict[each]['supervisor_pms']
            except Exception as e:
                raise e

            eachrow = [
                allowed_and_needed_nodes_dict[each]['pms']
                ,sup_pms
                ,allowed_and_needed_nodes_dict[each]['last_name']
                ,allowed_and_needed_nodes_dict[each]['first_name']
                ,allowed_and_needed_nodes_dict[each]['office_title']
                ,allowed_and_needed_nodes_dict[each]['civil_title']
                ,allowed_and_needed_nodes_dict[each]['wu_desc']
            ]
            writer.writerow(eachrow)


        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "post_data": dummy_in_mem_file.getvalue(),
        })
    except Exception as e:
        err_msg = "Exception: OrgChartPortal: GetEmpCsv(): {}".format(e)
        print(err_msg)
        return JsonResponse({
            "post_success": False,
            "post_msg": err_msg
        })


def GetCommissionerPMS(request):
    ## Authenticate User
    remote_user = None
    if request.user.is_authenticated:
        remote_user = request.user.username
    else:
        print('Warning: OrgChartPortal: GetCommissionerPMS(): UNAUTHENTICATE USER!')
        return JsonResponse({
            "post_success": False,
            "post_msg": "OrgChartPortal: GetCommissionerPMS():\n\nUNAUTHENTICATE USER!",
        })


    ## Read the json request body
    try:
        json_blob = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "post_success": False,
            "post_msg": "OrgChartPortal: GetCommissionerPMS():\n\nUnable to load request.body as a json object: {}".format(e),
        })

    ## Get the data
    try:
        # ## Check for Active Admins
        # is_admin = user_is_active_admin(remote_user)["isAdmin"]
        # if not is_admin:
        #     raise ValueError(f"'{remote_user}' is not admin. Only admins can access the GetCommissionerPMS() api")


        from WebAppsMain.secret_settings import OrgChartRootPMS

        emp_data = TblEmployees.objects.using('OrgChartRead').filter(
            pms__exact=f'{OrgChartRootPMS}',
        ).first()

        pms = emp_data.pms

        return JsonResponse({
            "post_success": True,
            "post_msg": None,
            "post_data": pms,
        })
    except Exception as e:
        err_msg = "Exception: OrgChartPortal: GetCommissionerPMS(): {}".format(e)
        print(err_msg)
        return JsonResponse({
            "post_success": False,
            "post_msg": err_msg
        })
