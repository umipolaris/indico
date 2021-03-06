<%inherit file="ConfDisplayBodyBase.tpl"/>

<%block name="title">
    ${body_title}
</%block>

<%block name="content">
    <div class="speakerIndexFiltersContainer">
        <div>
            <input type="text" id="filter_text" value="" placeholder="${ _('Search in speakers') }" />
        </div>
        <div class="speakerIndexFilteredText">
            ${_("Displaying ")}<span style="font-weight:bold;" id="numberFiltered">${len(items)}</span>
            <span id="numberFilteredText">${ _("speaker") if len(items) == 1 else _("speakers")}</span>
            ${_("out of")}
            <span style="font-weight:bold;">${len(items)}</span>
        </div>
    </div>
    <div class="speakerIndex index">
        % for key, item in items.iteritems():
            <div class="speakerIndexItem item">
                <div style="padding-bottom: 10px">
                    <span class="speakerIndexItemText text">${item[0]['fullName']}</span>
                    % if item[0]['affiliation']:
                        <span style="color: #888">(${item[0]['affiliation']})</span>
                    % endif
                </div>
                % for i in range(1, len(item)):
                    <div class="contribItem">
                        <a href="${item[i]['url']}">${item[i]['title']}</a>
                        % if item[i]['attached_items']:
                            ${ render_template('attachments/mako_compat/attachments_button.html', attached_items=item[i]['attached_items']) }
                        % endif
                    </div>
                % endfor
            </div>
        % endfor
    </div>
    <script>
        setupAttachmentTooltipButtons();
    </script>
</%block>
