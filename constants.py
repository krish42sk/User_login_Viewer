"""
constants.py

Defines which fields are editable for each user role in the application.
"""

EDITABLE_FIELDS = {
    '"public"."production_inputs"': {
        "rfdb_production_leaders": [
            "rfdb_production_emp_id",
            "rfdb_allotted_date", "rfdb_completed_date",
            "rfdb_production_time_taken", "rfdb_production_status",
            "rfdb_production_actual_road_type", "rfdb_production_remarks"
        ],

        "siloc_production_leaders": [
            "siloc_production_emp_id",
            "siloc_production_allotted_date", "siloc_production_completed_date",
            "siloc_production_time_taken", "siloc_production_sign_count",
            "siloc_production_autodetection_status", "siloc_production_status",
            "siloc_production_remarks"
        ],

        "siloc_qc_leaders": [
            "siloc_qc_emp_id",
            "siloc_qc_allotted_date", "siloc_qc_completed_date",
            "siloc_qc_time_taken", "siloc_qc_sign_count",
            "siloc_qc_status", "siloc_qc_remarks"
        ],

        "rfdb_qc_leaders": [
            "rfdb_qc_emp_id",
            "rfdb_qc_allotted_date", "rfdb_qc_completed_date",
            "rfdb_qc_time_taken", "rfdb_qc_status",
            "rfdb_qc_remarks", "rfdb_attri_qc_emp_id",
            "rfdb_attri_qc_allotted_date", "rfdb_attri_qc_completed_date",
            "rfdb_attri_qc_time_taken", "rfdb_attri_qc_status",
            "rfdb_attri_qc_remarks", "rfdb_roadtype_qc_emp_id",
            "rfdb_roadtype_qc_allotted_date", "rfdb_roadtype_qc_completed_date",
            "rfdb_roadtype_qc_time_taken", "rfdb_roadtype_qc_status",
            "rfdb_roadtype_qc_remarks", "rfdb_qa_emp_id",
            "rfdb_qa_done_by", "rfdb_qa_allotted_date",
            "rfdb_qa_completed_date", "rfdb_qa_time_taken",
            "rfdb_qa_status", "rfdb_qa_remarks",
            "delivery_status", "delivered_date"
        ],

        "grand_leaders": [
            "rfdb_production_team_leader_emp_id",
            "siloc_production_team_leader_emp_id",
            "siloc_qc_team_leader_emp_id",
            "rfdb_path_association_production_team_leader_emp_id",
            "rfdb_qc_team_leader_emp_id",
            "rfdb_attri_qc_team_leader_emp_id",
            "rfdb_path_association_qc_team_leader_emp_id",
            "rfdb_production_emp_id",
            "rfdb_allotted_date", "rfdb_completed_date",
            "rfdb_production_time_taken", "rfdb_production_status",
            "rfdb_production_actual_road_type", "rfdb_production_remarks",
            "siloc_production_emp_id",
            "siloc_production_allotted_date", "siloc_production_completed_date",
            "siloc_production_time_taken", "siloc_production_sign_count",
            "siloc_production_autodetection_status", "siloc_production_status",
            "siloc_production_remarks", "siloc_qc_emp_id",
            "siloc_qc_allotted_date", "siloc_qc_completed_date",
            "siloc_qc_time_taken", "siloc_qc_sign_count",
            "siloc_qc_status", "siloc_qc_remarks",
            "rfdb_path_association_production_emp_id",
            "rfdb_path_association_production_allotted_date",
            "rfdb_path_association_production_completed_date",
            "rfdb_path_association_production_time_taken",
            "rfdb_path_association_production_status",
            "rfdb_path_association_production_remarks",
            "rfdb_qc_emp_id", "rfdb_qc_allotted_date",
            "rfdb_qc_completed_date", "rfdb_qc_time_taken",
            "rfdb_qc_status", "rfdb_qc_remarks",
            "rfdb_attri_qc_emp_id", "rfdb_attri_qc_allotted_date",
            "rfdb_attri_qc_completed_date", "rfdb_attri_qc_time_taken",
            "rfdb_attri_qc_status", "rfdb_attri_qc_remarks",
            "rfdb_roadtype_qc_emp_id", "rfdb_roadtype_qc_allotted_date",
            "rfdb_roadtype_qc_completed_date", "rfdb_roadtype_qc_time_taken",
            "rfdb_roadtype_qc_status", "rfdb_roadtype_qc_remarks",
            "rfdb_qa_emp_id", "rfdb_qa_done_by",
            "rfdb_qa_allotted_date", "rfdb_qa_completed_date",
            "rfdb_qa_time_taken", "rfdb_qa_status",
            "rfdb_qa_remarks", "rfdb_path_association_qc_emp_id",
            "rfdb_path_association_qc_allotted_date",
            "rfdb_path_association_qc_completed_date",
            "rfdb_path_association_qc_time_taken",
            "rfdb_path_association_qc_status",
            "rfdb_path_association_qc_remarks",
            "delivery_status", "delivered_date"
        ]
    },
    
    '"public"."tm_production_inputs"': {
        "grand_leaders": [
            "priority", "intersection_type", "extracted_work_unit_id", "turn_maneuver_extraction_type",
            "auto_turn_maneuver_path_count", "manual_turn_maneuver_path_count", "rfdb_production_team_leader_emp_id",
            "rfdb_production_emp_id", "rfdb_allotted_date", "rfdb_completed_date", "rfdb_production_extraction_time_taken",
            "rfdb_production_correction_time_taken", "rfdb_production_status", "rfdb_ssd_jira_id",
            "rfdb_production_hold_reason", "rfdb_production_remarks", "rfdb_qc_team_leader_emp_id", "rfdb_qc_emp_id",
            "rfdb_qc_allotted_date", "rfdb_qc_completed_date", "rfdb_qc_first_review_time_taken",
            "rfdb_qc_second_review_time_taken", "rfdb_qc_total_tm_path_count", "rfdb_qc_status", "rfdb_qc_total_errors_marked",
            "rfdb_qc_ssd_jira_id", "rfdb_qc_hold_reason", "rfdb_qc_remarks", "siloc_team_leader_emp_id", "siloc_emp_id",
            "siloc_allotted_date", "siloc_completed_date", "siloc_time_taken", "siloc_sign_count", "siloc_status",
            "siloc_remarks", "siloc_ssd_jira_id", "siloc_hold_reason", "delivery_plugin_version_used",
            "delivery_extraction_guide_used", "delivery_status", "delivery_date"
            ],

        "rfdb_production_leaders": [
            "priority", "intersection_type", "extracted_work_unit_id", "turn_maneuver_extraction_type",
            "auto_turn_maneuver_path_count", "manual_turn_maneuver_path_count", "rfdb_production_emp_id",
            "rfdb_allotted_date", "rfdb_completed_date", "rfdb_production_extraction_time_taken",
            "rfdb_production_correction_time_taken", "rfdb_production_status", "rfdb_ssd_jira_id",
            "rfdb_production_hold_reason", "rfdb_production_remarks", "rfdb_qc_status"
            ],

        "rfdb_qc_leaders": [
            "rfdb_qc_emp_id", "rfdb_qc_allotted_date", "rfdb_qc_completed_date", "rfdb_qc_first_review_time_taken",
            "rfdb_qc_second_review_time_taken", "rfdb_qc_total_tm_path_count", "rfdb_qc_status",
            "rfdb_qc_total_errors_marked", "rfdb_qc_ssd_jira_id", "rfdb_qc_hold_reason", "rfdb_qc_remarks"                        
            ],

        "rfdb_production_user": [     
            "extracted_work_unit_id", "turn_maneuver_extraction_type", "auto_turn_maneuver_path_count",
            "manual_turn_maneuver_path_count", "rfdb_completed_date", "rfdb_production_extraction_time_taken",
            "rfdb_production_correction_time_taken", "rfdb_production_status", "rfdb_ssd_jira_id",
            "rfdb_production_hold_reason", "rfdb_production_remarks"                   
            ],

        "rfdb_qc_user": [       
            "rfdb_qc_completed_date", "rfdb_qc_first_review_time_taken", "rfdb_qc_second_review_time_taken",
            "rfdb_qc_total_tm_path_count", "rfdb_qc_status", "rfdb_qc_total_errors_marked",
            "rfdb_qc_ssd_jira_id", "rfdb_qc_hold_reason", "rfdb_qc_remarks"      
            ],

        "siloc_qc_leaders": [     
            "siloc_emp_id", "siloc_allotted_date", "siloc_completed_date", "siloc_time_taken",
            "siloc_sign_count", "siloc_status", "siloc_remarks", "siloc_ssd_jira_id",
            "siloc_hold_reason", "delivery_plugin_version_used", "delivery_extraction_guide_used",
            "delivery_status", "delivery_date"
            ],

        "siloc_production_leaders": [
            "siloc_emp_id", "siloc_allotted_date", "siloc_completed_date", "siloc_time_taken",
            "siloc_sign_count", "siloc_status", "siloc_remarks", "siloc_ssd_jira_id", "siloc_hold_reason"
            ],

        "siloc_production_user": [
            "siloc_completed_date", "siloc_time_taken", "siloc_sign_count", "siloc_status",
            "siloc_remarks", "siloc_ssd_jira_id", "siloc_hold_reason"
            ],

        "siloc_qc_user": [
            "siloc_completed_date", "siloc_time_taken", "siloc_sign_count", "siloc_status",
            "siloc_remarks", "siloc_ssd_jira_id", "siloc_hold_reason"
            ]            
    }
}


EMP_ID_TO_NAME_FIELDS = {
    "rfdb_production_team_leader_emp_id": "rfdb_production_team_leader_emp_name",
    "rfdb_production_emp_id": "rfdb_production_done_by",
    "siloc_production_team_leader_emp_id": "siloc_production_team_leader_emp_name",
    "siloc_production_emp_id": "siloc_production_done_by",
    "siloc_qc_team_leader_emp_id": "siloc_qc_team_leader_emp_name",
    "siloc_qc_emp_id": "siloc_qc_done_by",
    "rfdb_path_association_production_team_leader_emp_id": "rfdb_path_association_production_team_leader_emp_name",
    "rfdb_path_association_production_emp_id": "rfdb_path_association_production_done_by",
    "rfdb_qc_team_leader_emp_id": "rfdb_qc_team_leader_emp_name",
    "rfdb_qc_emp_id": "rfdb_qc_done_by",
    "rfdb_attri_qc_team_leader_emp_id": "rfdb_attri_qc_team_leader_emp_name",
    "rfdb_attri_qc_emp_id": "rfdb_attri_qc_done_by",
    "rfdb_roadtype_qc_emp_id": "rfdb_roadtype_qc_done_by",
    "rfdb_qa_emp_id": "rfdb_qa_done_by",
    "rfdb_path_association_qc_team_leader_emp_id": "rfdb_path_association_qc_team_leader_emp_name",
    "rfdb_path_association_qc_emp_id": "rfdb_path_association_qc_done_by"
}
