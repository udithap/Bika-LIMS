jQuery( function($) {

$(document).ready(function(){

	$(".ajax_calculate").live('change', function(){
		form_id = $(this).parents("form").attr("id");
		td = $(this).parents('td');
		uid = $(this).attr('uid');
		field = $(this).attr('field');
		value = $(this).attr('value');
		item_data = $(this).parents('table').prev('input[name="item_data"]').val();

//		$(td).attr('class', classname);

		// clear out the alerts for this field
		$(".alert").filter("span[uid='"+$(this).attr("uid")+"']").empty();

		if ($(this).parents('td').last().hasClass('interim')){
			// add value to form's item_data
			item_data = $.parseJSON(item_data);
			for(i = 0; i < item_data[uid].length;i++){
				if(item_data[uid][i]['keyword'] == field){
					item_data[uid][i]['value'] = value;
					item_data = $.toJSON(item_data);
					$(this).parents('table').prev('input[name="item_data"]').val(item_data);
					break;
				}
			}
		}

		// collect all form results into a hash (by analysis UID)
		var results = {};
		$.each($("input[field='Result'], select[field='Result']"), function(i, e){
			results[$(e).attr("uid")] = $(e).val();
		});

		options = {
			type: 'POST',
			url: 'listing_string_entry',
			data: {
				'_authenticator': $('input[name="_authenticator"]').val(),
				'uid': uid,
				'field': field,
				'value': value,
				'results': $.toJSON(results),
				'item_data': item_data,
				'specification': $(".specification")
					.filter(".selected").attr("value")
			},
			dataType: "json",
			success: function(data,textStatus,$XHR){
				// clear out all row alerts for rows with fresh results
				for(i=0;i<$(data['results']).length;i++){
					result = $(data['results'])[i];
					$(".alert").filter("span[uid='"+result.uid+"']").empty();
				}
				// put new alerts
				for(i=0;i<$(data['alerts']).length;i++){
					lert = $(data['alerts'])[i];
					$("span[uid='"+lert.uid+"']")
					  .filter("span[field='"+lert.field+"']")
					  .empty()
					  .append("<img src='++resource++bika.lims.images/"	+
						lert.icon +".png' title='"+
						lert.msg+"' uid='"+
						lert.uid+"' icon='"+
						lert.icon+"'/>");
				}
				// Update uncertainty value
				for(i=0;i<$(data['uncertainties']).length;i++){
					u = $(data['uncertainties'])[i];
					$('#'+u.uid+"-uncertainty").val(u.uncertainty);
				}
				// put result values in their boxes
				for(i=0;i<$(data['results']).length;i++){
					result = $(data['results'])[i];

					$("input[uid='"+result.uid+"']").filter("input[field='Result']").val(result.result);

					$('[type=hidden]').filter("[field=ResultDM]").filter("[uid="+result.uid+"]").val(result.dry_result);
					$($('[type=hidden]').filter("[field=ResultDM]").filter("[uid="+result.uid+"]").siblings()[0]).empty().append(result.dry_result);
					if(result.dry_result != ''){
						$($('[type=hidden]').filter("[field=ResultDM]").filter("[uid="+result.uid+"]").siblings().filter(".after")).empty().append("<em class='discreet'>%</em>")
					}

					$("input[uid='"+result.uid+"']").filter("input[field='formatted_result']").val(result.formatted_result);
					$("span[uid='"+result.uid+"']").filter("span[field='formatted_result']").empty().append(result.formatted_result);

					// check box
					if (results != ''){
						if ($('#'+form_id+'_cb_'+result.uid).attr('checked') == false) {
							$('#'+form_id+'_cb_'+result.uid).click();
						}
					}
				}
			}
		}
		$.ajax(options);
	});

	// range specification links
	$(".specification").click(function(event){
		tables = $(".bika-listing-table");
		event.preventDefault();
		for(t=0; t<tables.length; t++){
			table = tables[t];
			specs = $.parseJSON($(table).siblings('input[name="specs"]').val());
			result_elements = $(table).find('input[field="Result"]');
			for(i=0; i<result_elements.length; i++){
				re = result_elements[i];
				result = $(re).val();
				uid = $(re).attr('uid');
				st_uid = $(re).attr('st_uid');
				// remove old alerts
				$("img[uid='"+uid+"']").filter("img[icon='warning']").remove();
				$("img[uid='"+uid+"']").filter("img[icon='exclamation']").remove();
				if (result == ''){
					continue
				}
				spec = specs[st_uid];
				if (spec == undefined){
					continue;
				}
				// get spec data from TR
				specification = $(this).attr('value');
				if (!specification in spec) {
					continue;
				}
				if (spec.length == 0) {
					continue;
				}
				spec = spec[specification];
				if (spec == undefined){
					continue;
				}
				re_spec = spec[$(re).attr("objectid")];
				if (re_spec == undefined || re_spec == null) {
					continue;
				}
				result = parseFloat(result);
				spec_min = parseFloat(re_spec.min);
				spec_max = parseFloat(re_spec.max);
				// shoulder first
				error_amount =  (result/100)*parseFloat(re_spec['error'])
				error_min = result - error_amount
				error_max = result + error_amount
				if (((result < spec_min) && (error_max >= spec_min)) ||
					((result > spec_max) && (error_min <= spec_max)) ){
					range_str = "min " + spec_min +
					            ", max " + spec_max +
								", error" + re_spec['error'] + "%";
					$("span[uid='"+uid+"']")
					  .filter("span[field='Result']")
					  .append("<img src='++resource++bika.lims.images/warning.png' uid='"+
					  uid+"' icon='warning' title='Result out of range ("+range_str+")'/>");
					continue;
				}
				// then check if in range
				if (result >= spec_min && result <= spec_max) {
					continue;
				}
				// fall to here; set red.
				range_str = "min: " + spec_min + ", max: " + spec_max;
				$("span[uid='"+uid+"']")
				  .filter("span[field='Result']")
				  .append("<img src='++resource++bika.lims.images/exclamation.png' uid='"+
				  uid+"' icon='exclamation' title='Result out of range ("+range_str+")'/>");
			}
		}
		if ($(this).attr('value') == 'lab') {
			$("a[id='client']").removeClass("selected");
			$("a[id='lab']").addClass("selected");
		}
		if ($(this).attr('value') == 'client') {
			$("a[id='client']").addClass("selected");
			$("a[id='lab']").removeClass("selected");
		}
	});


});
});
