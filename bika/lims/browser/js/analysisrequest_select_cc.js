jQuery( function($) {
$(document).ready(function(){

	_ = window.jsi18n;

	// ##cc_uids is the parent AR form's CC contacts box
	$.each(window.opener.$("#cc_uids").val().split(","), function(i,e){
		form_id = $(this).parents("form").attr("id");
		$("#"+form_id+"_cb_"+e).click();
	});

	// return selected references from the CC popup window back into the widget
	$('[transition=save]').click(function(){
		uids = [];
		titles = [];
		$.each($("[name='uids:list']").filter(":checked"), function(i, e){
			uids.push($(e).val());
			titles.push($(e).attr('item_title'));
		});
		window.opener.$("#cc_titles").val(titles.join(','));
		window.opener.$("#cc_uids").val(uids.join(','));
		window.close();
		return false;
	});

});
});
