"""
constants.py

Defines which fields are editable for each users role in the application.
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

        "rfdb_production_users": [     
            "extracted_work_unit_id", "turn_maneuver_extraction_type", "auto_turn_maneuver_path_count",
            "manual_turn_maneuver_path_count", "rfdb_completed_date", "rfdb_production_extraction_time_taken",
            "rfdb_production_correction_time_taken", "rfdb_production_status", "rfdb_ssd_jira_id",
            "rfdb_production_hold_reason", "rfdb_production_remarks"                   
            ],

        "rfdb_qc_users": [       
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

        "siloc_production_users": [
            "siloc_completed_date", "siloc_time_taken", "siloc_sign_count", "siloc_status",
            "siloc_remarks", "siloc_ssd_jira_id", "siloc_hold_reason"
            ],

        "siloc_qc_users": [
            "siloc_completed_date", "siloc_time_taken", "siloc_sign_count", "siloc_status",
            "siloc_remarks", "siloc_ssd_jira_id", "siloc_hold_reason"
            ]            
    }
}


INTERSECTION_TYPE_VALUES = [
    "Valid In-In TM Location",
    "Valid In-In Ramp Extension (Data not available)",
    "Invalid In-In No TM Location",
    "Invalid In-In Duplicate Nodes",
    "Invalid In-In Bifurcation Ramp Extension (Data available)",
    "Invalid In-In Bifurcation Highway Ramp",
    "In-Out /Out-In"
]

TURN_MANEUVER_EXTRACTION_TYPE_VALUES = [
    "Auto", "Manual", "U-Turn", "In-Out"
]

RFDB_PRODUCTION_STATUS_VALUES = [
    "Completed", "Inprogress", "Yet to start", "Hold", "Doubt_Case"
]

RFDB_QC_STATUS_VALUES = [
    "Completed", "Inprogress", "Yet to start", "Hold", "QC_Rejected", "Rework_Inprogress", "Rework_Completed", "Doubt_Case"
]

SILOC_STATUS_VALUES = [
    "Completed", "Inprogress", "Yet to start", "Hold", "Doubt_Case"
]

DELIVERY_STATUS_VALUES = [
    "Delivered", "Undelivered", "Hold"
]

DATE_COLUMNS = [
    "wu_received_date", "rfdb_allotted_date", "rfdb_completed_date",
    "rfdb_qc_allotted_date", "rfdb_qc_completed_date", "siloc_allotted_date",
    "siloc_completed_date", "delivery_date"
]